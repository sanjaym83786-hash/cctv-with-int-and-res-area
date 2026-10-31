"""
Tests for backend/usecases/intrusion.py — IntrusionDetector
"""

from __future__ import annotations

import datetime
from unittest.mock import patch, MagicMock

import pytest

from backend.usecases.intrusion import IntrusionDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_track(track_id: int = 1, cls: str = "person", bbox=None):
    """Return a minimal track dict compatible with IntrusionDetector."""
    if bbox is None:
        bbox = [100, 200, 200, 400]
    return {"track_id": track_id, "class": cls, "bbox": bbox, "confidence": 0.9}


def _dt(hour: int, minute: int = 0, second: int = 0) -> datetime.datetime:
    """Return a datetime on an arbitrary fixed date with the given time."""
    return datetime.datetime(2024, 6, 15, hour, minute, second)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestIntrusionDetector:
    # ------------------------------------------------------------------
    # Fixture: default detector armed 22:00 → 06:00
    # ------------------------------------------------------------------

    @pytest.fixture()
    def detector(self):
        return IntrusionDetector(armed_hours=(22, 6), cooldown_seconds=30)

    # ------------------------------------------------------------------
    # 1. No alert outside armed hours (noon)
    # ------------------------------------------------------------------

    def test_no_alert_outside_armed_hours(self, detector):
        now = _dt(12, 0)  # noon — disarmed
        tracks = [_make_track(1), _make_track(2)]
        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = detector.process(tracks, frame=None)
        assert alerts == [], f"Expected no alerts at noon, got {alerts}"

    # ------------------------------------------------------------------
    # 2. Alert during armed hours — 23:00
    # ------------------------------------------------------------------

    def test_alert_during_armed_hours_midnight(self, detector):
        now = _dt(23, 0)
        tracks = [_make_track(1)]
        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = detector.process(tracks, frame=None)
        assert len(alerts) == 1
        assert alerts[0]["track_id"] == 1

    # ------------------------------------------------------------------
    # 3. Alert during armed hours — 03:00
    # ------------------------------------------------------------------

    def test_alert_during_armed_hours_early_morning(self, detector):
        now = _dt(3, 0)
        tracks = [_make_track(1)]
        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = detector.process(tracks, frame=None)
        assert len(alerts) == 1

    # ------------------------------------------------------------------
    # 4. Cooldown suppresses duplicate alerts
    # ------------------------------------------------------------------

    def test_cooldown_suppresses_duplicate_alerts(self, detector):
        now = _dt(23, 0)
        track = _make_track(1)

        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            first_alerts = detector.process([track], frame=None)

        # Second call at the same time — still within cooldown
        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            second_alerts = detector.process([track], frame=None)

        assert len(first_alerts) == 1, "First call should yield an alert"
        # Same track within cooldown window → suppressed
        track_ids_second = [a["track_id"] for a in second_alerts]
        assert 1 not in track_ids_second, "Duplicate alert should be suppressed by cooldown"

    # ------------------------------------------------------------------
    # 5. Cooldown expires — alert fires again after 31 s
    # ------------------------------------------------------------------

    def test_cooldown_expires(self, detector):
        t0 = _dt(23, 0, 0)
        t1 = _dt(23, 0, 31)  # 31 seconds later — past 30 s cooldown
        track = _make_track(1)

        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t0
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            detector.process([track], frame=None)

        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = t1
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = detector.process([track], frame=None)

        assert len(alerts) == 1, "Alert should fire again after cooldown expires"

    # ------------------------------------------------------------------
    # 6. Non-person class ignored
    # ------------------------------------------------------------------

    def test_non_person_class_ignored(self, detector):
        now = _dt(23, 0)
        track = _make_track(1, cls="car")
        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = detector.process([track], frame=None)
        assert alerts == [], "Non-person tracks should not trigger intrusion alerts"

    # ------------------------------------------------------------------
    # 7. Person class triggers alert
    # ------------------------------------------------------------------

    def test_person_class_triggers(self, detector):
        now = _dt(23, 0)
        track = _make_track(1, cls="person")
        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = detector.process([track], frame=None)
        assert len(alerts) == 1

    # ------------------------------------------------------------------
    # 8. Multiple tracks → 3 separate alerts with distinct track_ids
    # ------------------------------------------------------------------

    def test_multiple_tracks(self, detector):
        now = _dt(23, 0)
        tracks = [_make_track(i, cls="person") for i in range(1, 4)]
        with patch("backend.usecases.intrusion.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.side_effect = lambda *a, **kw: datetime.datetime(*a, **kw)
            alerts = detector.process(tracks, frame=None)

        assert len(alerts) == 3
        returned_ids = {a["track_id"] for a in alerts}
        assert returned_ids == {1, 2, 3}
