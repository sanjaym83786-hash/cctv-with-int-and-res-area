"""
Tests for backend/usecases/restricted_area.py — RestrictedAreaMonitor
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from backend.usecases.restricted_area import RestrictedAreaMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A simple axis-aligned square: (0,0)→(100,0)→(100,100)→(0,100)
SQUARE_ZONE = {
    "name": "zone_square",
    "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
}

# A second zone far away
REMOTE_ZONE = {
    "name": "zone_remote",
    "polygon": [[500, 500], [600, 500], [600, 600], [500, 600]],
}


def _make_track(track_id: int, bbox: list, cls: str = "person"):
    """Return a minimal track dict."""
    return {"track_id": track_id, "class": cls, "bbox": bbox, "confidence": 0.85}


def _dt(second: float = 0.0) -> datetime.datetime:
    """Return a datetime at t=second from a fixed epoch."""
    base = datetime.datetime(2024, 1, 1, 0, 0, 0)
    return base + datetime.timedelta(seconds=second)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestRestrictedAreaMonitor:
    # ------------------------------------------------------------------
    # Fixture: monitor with single square zone, loiter=5 s
    # ------------------------------------------------------------------

    @pytest.fixture()
    def monitor(self):
        return RestrictedAreaMonitor(zones=[SQUARE_ZONE], loiter_seconds=5)

    @pytest.fixture()
    def multi_monitor(self):
        return RestrictedAreaMonitor(zones=[SQUARE_ZONE, REMOTE_ZONE], loiter_seconds=5)

    # ------------------------------------------------------------------
    # _point_in_polygon tests
    # ------------------------------------------------------------------

    def test_point_in_polygon_inside(self, monitor):
        polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        assert monitor._point_in_polygon((50, 50), polygon) is True

    def test_point_in_polygon_outside(self, monitor):
        polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        assert monitor._point_in_polygon((150, 150), polygon) is False

    def test_point_in_polygon_on_edge(self, monitor):
        """
        A point exactly on or just inside an edge should not raise an error.
        The return value is implementation-defined for boundary cases, but
        the method must not throw.
        """
        polygon = [[0, 0], [100, 0], [100, 100], [0, 100]]
        # Should not raise; result is True or False
        result = monitor._point_in_polygon((0, 50), polygon)
        assert isinstance(result, bool)

    # ------------------------------------------------------------------
    # _bottom_center
    # ------------------------------------------------------------------

    def test_bottom_center_calculation(self, monitor):
        # bbox = [x1, y1, x2, y2] → bottom_center = ((x1+x2)/2, y2)
        bc = monitor._bottom_center([100, 200, 300, 400])
        assert bc == (200, 400), f"Expected (200, 400), got {bc}"

    # ------------------------------------------------------------------
    # Loitering threshold tests
    # ------------------------------------------------------------------

    def test_no_alert_below_loiter_threshold(self, monitor):
        """Track enters zone but hasn't loitered long enough."""
        # bbox with bottom_center (50, 50) — inside SQUARE_ZONE
        track = _make_track(1, [0, 0, 100, 100])
        t0 = _dt(0)
        t1 = _dt(3)  # only 3 seconds — below 5-second threshold

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t0
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            monitor.process([track], frame=None)

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t1
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = monitor.process([track], frame=None)

        assert alerts == [], f"Expected no alert before loiter threshold, got {alerts}"

    def test_alert_after_loiter_threshold(self, monitor):
        """Track loiters for >5 s → alert."""
        track = _make_track(1, [0, 0, 100, 100])
        t0 = _dt(0)
        t1 = _dt(6)  # 6 seconds — past threshold

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t0
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            monitor.process([track], frame=None)

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t1
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = monitor.process([track], frame=None)

        assert len(alerts) == 1

    def test_alert_contains_correct_zone_name(self, monitor):
        """Alert dict must include the zone name."""
        track = _make_track(1, [0, 0, 100, 100])
        t0 = _dt(0)
        t1 = _dt(6)

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t0
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            monitor.process([track], frame=None)

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t1
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = monitor.process([track], frame=None)

        assert len(alerts) == 1
        assert alerts[0]["zone_name"] == "zone_square"

    def test_track_outside_zone_no_alert(self, monitor):
        """Bottom center outside all zones → no alert even after long time."""
        # bbox with bottom_center (250, 250) — outside SQUARE_ZONE (0-100)
        track = _make_track(1, [200, 200, 300, 300])
        t0 = _dt(0)
        t1 = _dt(30)

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t0
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            monitor.process([track], frame=None)

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t1
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = monitor.process([track], frame=None)

        assert alerts == []

    # ------------------------------------------------------------------
    # Multiple zones
    # ------------------------------------------------------------------

    def test_multiple_zones(self, multi_monitor):
        """Track in zone1 only → alert for zone1, not zone2."""
        # bottom_center (50, 50) → inside SQUARE_ZONE, outside REMOTE_ZONE
        track = _make_track(1, [0, 0, 100, 100])
        t0 = _dt(0)
        t1 = _dt(6)

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t0
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            multi_monitor.process([track], frame=None)

        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t1
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = multi_monitor.process([track], frame=None)

        zone_names = [a["zone_name"] for a in alerts]
        assert "zone_square" in zone_names
        assert "zone_remote" not in zone_names

    # ------------------------------------------------------------------
    # Timer reset on exit
    # ------------------------------------------------------------------

    def test_track_exits_zone_resets_timer(self, monitor):
        """
        Track enters zone (t=0), loiters (t=6 → alert), exits (t=7),
        re-enters (t=8), timer resets, no alert at t=10 (only 2 s in zone).
        """
        inside_bbox = [0, 0, 100, 100]   # bottom_center (50, 50) — inside
        outside_bbox = [200, 200, 300, 300]  # bottom_center (250, 250) — outside
        track_in = _make_track(1, inside_bbox)
        track_out = _make_track(1, outside_bbox)

        # Phase 1: enter at t=0
        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _dt(0)
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            monitor.process([track_in], frame=None)

        # Phase 2: loiter fires at t=6
        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _dt(6)
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts_first = monitor.process([track_in], frame=None)

        # Phase 3: exit at t=7
        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _dt(7)
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            monitor.process([track_out], frame=None)

        # Phase 4: re-enter at t=8
        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _dt(8)
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            monitor.process([track_in], frame=None)

        # Phase 5: check at t=10 — only 2 s since re-entry, below threshold
        with patch("backend.usecases.restricted_area.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _dt(10)
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts_second = monitor.process([track_in], frame=None)

        assert len(alerts_first) == 1, "Should have alerted after initial loiter"
        assert alerts_second == [], "Timer should have reset after exit; no alert at t=10"
