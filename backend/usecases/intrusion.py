"""
backend/usecases/intrusion.py

Time-gated intrusion detection use-case.

The :class:`IntrusionDetector` raises alerts when a tracked object of a
configured class (default: ``"person"``) is observed during armed hours, subject
to a per-track cooldown to avoid alert floods.
"""

from __future__ import annotations

import logging
import datetime
from datetime import timedelta
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Default configuration values
_DEFAULT_CONFIG: dict = {
    "armed_hours": (22, 6),     # 10 PM – 6 AM
    "cooldown_seconds": 30,
    "target_classes": ["person"],
}


class IntrusionDetector:
    """Generates intrusion alerts for tracked objects during armed hours.

    Args:
        config: Optional override dict with any subset of the keys:

            * ``armed_hours`` (:class:`tuple[int, int]`) — ``(start_hour, end_hour)``
              in 24-hour local time.  The window **wraps midnight** when
              ``start_hour > end_hour``.
            * ``cooldown_seconds`` (:class:`int`) — minimum seconds between
              successive alerts for the same track.
            * ``target_classes`` (:class:`list[str]`) — labels that trigger alerts.

    Example::

        detector = IntrusionDetector({"armed_hours": (0, 24), "cooldown_seconds": 10})
        alerts = detector.process(tracks, datetime.now())
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        *,
        armed_hours: Optional[tuple[int, int] | list[int]] = None,
        cooldown_seconds: Optional[int] = None,
        target_classes: Optional[list[str]] = None,
    ) -> None:
        cfg = {**_DEFAULT_CONFIG, **(config or {})}
        if armed_hours is not None:
            cfg["armed_hours"] = armed_hours
        if cooldown_seconds is not None:
            cfg["cooldown_seconds"] = cooldown_seconds
        if target_classes is not None:
            cfg["target_classes"] = target_classes

        armed = cfg["armed_hours"]
        if not (isinstance(armed, (tuple, list)) and len(armed) == 2):
            raise ValueError(
                f"'armed_hours' must be a 2-element tuple (start, end), got {armed!r}."
            )
        self.armed_start: int = int(armed[0])
        self.armed_end: int = int(armed[1])
        self.cooldown_seconds: int = int(cfg["cooldown_seconds"])
        self.target_classes: list[str] = list(cfg["target_classes"])
        # Support 24/7 armed mode or enable/disable
        self.enabled: bool = bool(cfg.get("enabled", True))

        # Per-track timestamp of the last alert emitted
        self._last_alert: dict[int, Any] = {}
        logger.info(
            "IntrusionDetector configured: armed=%02d:00–%02d:00, "
            "cooldown=%ds, targets=%s.",
            self.armed_start,
            self.armed_end,
            self.cooldown_seconds,
            self.target_classes,
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _is_armed(self, check_time: Optional[Any] = None) -> bool:
        """Return ``True`` when the given or current local hour is within the armed window.

        Handles 24/7 armed ((0, 24) or (0, 0)) and midnight wraparound (e.g. 22:00 → 06:00).
        """
        if not self.enabled:
            return False
        if (self.armed_start == 0 and self.armed_end in (24, 0)) or (self.armed_start == self.armed_end and self.armed_start == 0):
            return True

        if check_time is not None and hasattr(check_time, "hour"):
            hour = check_time.hour
        else:
            now_val = datetime.datetime.now()
            hour = now_val.hour if hasattr(now_val, "hour") else 0

        if self.armed_start <= self.armed_end:
            # Normal window (e.g. 08:00 – 20:00)
            return self.armed_start <= hour < self.armed_end
        else:
            # Wraps midnight (e.g. 22:00 – 06:00)
            return hour >= self.armed_start or hour < self.armed_end

    def _is_in_cooldown(self, track_id: int, frame_time: Any) -> bool:
        """Return ``True`` if an alert for *track_id* was recently emitted."""
        last = self._last_alert.get(track_id)
        if last is None:
            return False
        diff = frame_time - last
        secs = diff.total_seconds() if hasattr(diff, "total_seconds") else float(diff)
        return secs < float(self.cooldown_seconds)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def process(
        self,
        tracks: list[dict],
        frame_time: Optional[Any] = None,
        frame: Any = None,
    ) -> list[dict]:
        """Evaluate confirmed tracks and produce intrusion alert dicts.

        Args:
            tracks:     List of track dicts as returned by
                        :meth:`~backend.tracker.tracker.ByteTracker.update`,
                        each containing at minimum ``track_id``, ``bbox``,
                        and ``label`` (or ``class``).
            frame_time: Timestamp to associate with any emitted alerts. Also
                        used for cooldown calculations. Defaults to datetime.now().
            frame:      Optional frame image (for compatibility).

        Returns:
            List of alert dicts (may be empty).
        """
        if frame_time is None:
            frame_time = datetime.datetime.now()

        if not self._is_armed(frame_time):
            return []

        alerts: list[dict] = []
        for track in tracks:
            label = track.get("label") or track.get("class") or ""
            if label not in self.target_classes:
                continue

            track_id: int = track["track_id"]
            if self._is_in_cooldown(track_id, frame_time):
                continue

            self._last_alert[track_id] = frame_time
            iso_time = frame_time.isoformat() if hasattr(frame_time, "isoformat") else str(frame_time)
            alert = {
                "type": "intrusion",
                "track_id": track_id,
                "bbox": track["bbox"],
                "timestamp": iso_time,
                "message": (
                    f"Intrusion alert: {label} (track #{track_id}) detected "
                    f"during armed hours ({self.armed_start:02d}:00–"
                    f"{self.armed_end:02d}:00)."
                ),
            }
            alerts.append(alert)
            logger.warning(alert["message"])

        return alerts
