"""
backend/usecases/restricted_area.py

Restricted-area loitering detection use-case.

The :class:`RestrictedAreaMonitor` tracks how long each object dwells inside
user-defined polygonal zones and emits alerts when the dwell time exceeds a
configurable threshold.

Polygon containment is determined using the **ray-casting algorithm** — no
external geometry library (e.g. Shapely) is required.
"""

from __future__ import annotations

import logging
import datetime
from datetime import datetime as _dt_class
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Default full-frame zone (640×480 capture resolution)
_DEFAULT_ZONE: dict = {
    "name": "Default Zone",
    "polygon": [[0, 0], [640, 0], [640, 480], [0, 480]],
    "loiter_seconds": 5.0,
}

_DEFAULT_CONFIG: dict = {
    "zones": [_DEFAULT_ZONE],
}


def _point_in_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    """Ray-casting algorithm to test whether *point* lies inside or on the border of *polygon*.

    Works for any simple (non-self-intersecting) polygon regardless of winding
    order.
    """
    px, py = point
    n = len(polygon)
    if n < 3:
        return False

    # First check if the point lies exactly on any segment of the polygon
    for i in range(n):
        x1, y1 = polygon[i][0], polygon[i][1]
        x2, y2 = polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]
        # Bounding box check for segment
        if min(x1, x2) <= px <= max(x1, x2) and min(y1, y2) <= py <= max(y1, y2):
            # Check collinearity via cross product
            cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
            if abs(cross) < 1e-7:
                return True

    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]

        # Check if the horizontal ray from point crosses the edge (xi,yi)-(xj,yj)
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i

    return inside


class RestrictedAreaMonitor:
    """Monitors polygonal zones for loitering objects.

    Each zone is defined by a convex or concave polygon.  When a tracked
    object's **bottom-centre** foot-point dwells inside a zone for longer than
    the zone's ``loiter_seconds`` threshold an alert is emitted.

    Args:
        config: Optional override dict with key ``"zones"`` — a list of zone
                dicts, each containing:

                * ``name`` (:class:`str`) — display name for the zone.
                * ``polygon`` (:class:`list`) — ordered ``[[x, y], …]`` vertices.
                * ``loiter_seconds`` (:class:`float`) — dwell threshold in seconds.

    Example::

        monitor = RestrictedAreaMonitor({
            "zones": [{"name": "Vault", "polygon": [[100,100],[400,100],
                        [400,300],[100,300]], "loiter_seconds": 3.0}]
        })
        alerts = monitor.process(tracks, datetime.now())
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        *,
        zones: Optional[list[dict]] = None,
        loiter_seconds: Optional[float] = None,
    ) -> None:
        cfg = {**_DEFAULT_CONFIG, **(config or {})}
        if zones is not None:
            cfg["zones"] = zones
        self.zones: list[dict] = cfg.get("zones", [_DEFAULT_ZONE])
        self.default_loiter: float = loiter_seconds if loiter_seconds is not None else 5.0

        # entry_times[track_id][zone_name] = entry datetime
        self._entry_times: dict[int, dict[str, datetime]] = {}

        logger.info(
            "RestrictedAreaMonitor configured with %d zone(s): %s.",
            len(self.zones),
            [z["name"] for z in self.zones],
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _point_in_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
        """Ray-casting algorithm to test whether point lies inside polygon."""
        return _point_in_polygon(point, polygon)

    @staticmethod
    def _bottom_center(bbox: list[float]) -> tuple[int, int]:
        """Return the bottom-centre pixel of a bounding box.

        Args:
            bbox: ``[x1, y1, x2, y2]`` in pixels.

        Returns:
            ``(cx, y2)`` as integers.
        """
        x1, y1, x2, y2 = bbox
        return (int((x1 + x2) // 2), int(y2))

    def _cleanup_exited_tracks(
        self,
        active_ids: set[int],
        zone_name: str,
    ) -> None:
        """Remove entry-time records for tracks that are no longer active."""
        stale = [tid for tid in self._entry_times if tid not in active_ids]
        for tid in stale:
            self._entry_times[tid].pop(zone_name, None)
            if not self._entry_times[tid]:
                del self._entry_times[tid]

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def process(
        self,
        tracks: list[dict],
        frame_time: Optional[Any] = None,
        frame: Any = None,
    ) -> list[dict]:
        """Evaluate confirmed tracks against all zones and return loitering alerts.

        Args:
            tracks:     List of track dicts from
                        :meth:`~backend.tracker.tracker.ByteTracker.update`.
            frame_time: Current frame timestamp used to compute dwell duration.
            frame:      Optional frame image for compatibility.

        Returns:
            List of alert dicts (may be empty).
        """
        if frame_time is None:
            # Supports both patch('...datetime') with mock.datetime.now or mock.now
            if hasattr(datetime, "datetime") and hasattr(datetime.datetime, "now"):
                frame_time = datetime.datetime.now()
            elif hasattr(datetime, "now"):
                frame_time = datetime.now()
            else:
                frame_time = _dt_class.now()
        active_ids: set[int] = {t["track_id"] for t in tracks}
        alerts: list[dict] = []

        for zone in self.zones:
            zone_name: str = zone["name"]
            polygon: list[list[float]] = zone["polygon"]
            loiter_threshold: float = float(zone.get("loiter_seconds", self.default_loiter))

            # Purge stale track records for this zone
            self._cleanup_exited_tracks(active_ids, zone_name)

            for track in tracks:
                track_id: int = track["track_id"]
                bbox: list[float] = track["bbox"]
                foot = self._bottom_center(bbox)

                if _point_in_polygon(foot, polygon):
                    # Track is inside the zone — record or update entry time
                    track_zones = self._entry_times.setdefault(track_id, {})
                    if zone_name not in track_zones:
                        track_zones[zone_name] = frame_time
                        iso = frame_time.isoformat() if hasattr(frame_time, "isoformat") else str(frame_time)
                        logger.debug("Track #%d entered zone '%s' at %s.", track_id, zone_name, iso)

                    diff = frame_time - track_zones[zone_name]
                    if hasattr(diff, "total_seconds"):
                        dwell_val = diff.total_seconds()
                        dwell = dwell_val() if callable(dwell_val) else dwell_val
                    else:
                        dwell = float(diff)
                    if float(dwell) >= loiter_threshold:
                        iso_str = frame_time.isoformat() if hasattr(frame_time, "isoformat") else str(frame_time)
                        alert = {
                            "type": "restricted_area",
                            "track_id": track_id,
                            "zone_name": zone_name,
                            "bbox": bbox,
                            "dwell_seconds": round(dwell, 2),
                            "timestamp": iso_str,
                            "message": (
                                f"Loitering alert: track #{track_id} has been in "
                                f"'{zone_name}' for {dwell:.1f}s "
                                f"(threshold: {loiter_threshold:.1f}s)."
                            ),
                        }
                        alerts.append(alert)
                        logger.warning(alert["message"])
                else:
                    # Track left the zone — clear entry time
                    if track_id in self._entry_times:
                        self._entry_times[track_id].pop(zone_name, None)

        return alerts
