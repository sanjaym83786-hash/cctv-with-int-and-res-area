"""
backend/tracker/tracker.py

Lightweight ByteTrack-lite multi-object tracker.

Implements a simplified version of the ByteTrack algorithm using IoU-based
Hungarian matching.  Tracks progress through three states:

* **tentative** — seen for fewer than ``min_hits`` frames.
* **confirmed** — seen for at least ``min_hits`` consecutive frames.
* **lost**       — not matched for up to ``max_age`` frames; then deleted.

Only *confirmed* tracks are returned from :meth:`ByteTracker.update`.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy.optimize import linear_sum_assignment

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Track state type
# --------------------------------------------------------------------------- #
TrackState = Literal["tentative", "confirmed", "lost"]

# --------------------------------------------------------------------------- #
# IoU helper
# --------------------------------------------------------------------------- #


def _iou(bbox_a: list[float], bbox_b: list[float]) -> float:
    """Compute Intersection-over-Union between two axis-aligned bounding boxes.

    Args:
        bbox_a: [x1, y1, x2, y2]
        bbox_b: [x1, y1, x2, y2]

    Returns:
        IoU in [0, 1].
    """
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union_area = area_a + area_b - inter_area

    return inter_area / union_area if union_area > 0 else 0.0


def _iou_matrix(tracks_bboxes: list[list[float]], det_bboxes: list[list[float]]) -> np.ndarray:
    """Build an IoU cost matrix (shape: ``[num_tracks, num_dets]``).

    Values are **cost** = 1 - IoU so that minimising the cost maximises IoU.
    """
    n_t = len(tracks_bboxes)
    n_d = len(det_bboxes)
    matrix = np.ones((n_t, n_d), dtype=np.float32)
    for i, tb in enumerate(tracks_bboxes):
        for j, db in enumerate(det_bboxes):
            matrix[i, j] = 1.0 - _iou(tb, db)
    return matrix


# --------------------------------------------------------------------------- #
# Track dataclass
# --------------------------------------------------------------------------- #

_track_id_counter = itertools.count(1)


@dataclass
class Track:
    """Represents a single tracked object over time.

    Attributes:
        id:     Unique integer identifier assigned at creation.
        bbox:   Most recent bounding box ``[x1, y1, x2, y2]``.
        hits:   Total number of times this track has been matched.
        age:    Frames since the track was last matched (0 = matched this frame).
        state:  One of ``"tentative"``, ``"confirmed"``, or ``"lost"``.
        class_id: COCO class index of the associated detection.
        label:  Human-readable class label.
        conf:   Detection confidence of the last matched detection.
    """

    id: int = field(default_factory=lambda: next(_track_id_counter))
    bbox: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    hits: int = 0
    age: int = 0
    state: TrackState = "tentative"
    class_id: int = 0
    label: str = ""
    conf: float = 0.0


# --------------------------------------------------------------------------- #
# ByteTracker
# --------------------------------------------------------------------------- #


class ByteTracker:
    """Simplified ByteTrack-lite multi-object tracker.

    Args:
        max_age:       Maximum number of consecutive unmatched frames before a
                       track is permanently deleted.
        min_hits:      Minimum consecutive matched frames before a track is
                       promoted to ``"confirmed"`` state.
        iou_threshold: IoU threshold below which a track-detection pair is
                       considered unmatched during Hungarian assignment.
    """

    def __init__(
        self,
        max_age: int = 30,
        min_hits: int = 3,
        iou_threshold: float = 0.3,
    ) -> None:
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self._tracks: list[Track] = []

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def update(self, detections: list[dict]) -> list[dict]:
        """Associate *detections* with existing tracks and update states.

        Uses the Hungarian algorithm (``scipy.optimize.linear_sum_assignment``)
        to minimise an IoU-based cost matrix.

        Args:
            detections: List of detection dicts from
                        :meth:`~backend.models.loader.ModelLoader.infer`, each
                        containing at minimum ``bbox``, ``conf``, ``class_id``
                        and ``label``.

        Returns:
            List of dicts for every *confirmed* track, each containing all
            original detection fields plus ``track_id`` (int).
        """
        # ── 1. Match detections to existing non-lost tracks ─────────────── #
        active_tracks = [t for t in self._tracks if t.state != "lost"]

        if active_tracks and detections:
            cost_matrix = _iou_matrix(
                [t.bbox for t in active_tracks],
                [d["bbox"] for d in detections],
            )
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
        else:
            row_ind, col_ind = np.array([], dtype=int), np.array([], dtype=int)

        matched_track_ids: set[int] = set()
        matched_det_ids: set[int] = set()

        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] > (1.0 - self.iou_threshold):
                # IoU too low — treat as unmatched
                continue
            track = active_tracks[r]
            det = detections[c]
            track.bbox = det["bbox"]
            track.conf = det["conf"]
            track.class_id = det["class_id"]
            track.label = det["label"]
            track.hits += 1
            track.age = 0
            matched_track_ids.add(r)
            matched_det_ids.add(c)

            if track.state == "tentative" and track.hits >= self.min_hits:
                track.state = "confirmed"

        # ── 2. Age unmatched active tracks ─────────────────────────────── #
        for i, track in enumerate(active_tracks):
            if i not in matched_track_ids:
                track.age += 1
                if track.age > self.max_age:
                    track.state = "lost"
                elif track.state == "confirmed":
                    # Keep confirmed but mark as potentially lost
                    pass

        # ── 3. Spawn new tracks for unmatched detections ────────────────── #
        for j, det in enumerate(detections):
            if j not in matched_det_ids:
                new_track = Track(
                    bbox=det["bbox"],
                    hits=1,
                    age=0,
                    state="tentative",
                    class_id=det["class_id"],
                    label=det["label"],
                    conf=det["conf"],
                )
                self._tracks.append(new_track)

        # ── 4. Prune permanently lost tracks ────────────────────────────── #
        self._tracks = [t for t in self._tracks if t.state != "lost"]

        # ── 5. Return confirmed tracks ──────────────────────────────────── #
        results: list[dict] = []
        for track in self._tracks:
            if track.state == "confirmed":
                results.append({
                    "track_id": track.id,
                    "bbox": track.bbox,
                    "conf": track.conf,
                    "class_id": track.class_id,
                    "label": track.label,
                })

        logger.debug(
            "ByteTracker: %d detections → %d active tracks (%d confirmed).",
            len(detections),
            len(self._tracks),
            len(results),
        )
        return results
