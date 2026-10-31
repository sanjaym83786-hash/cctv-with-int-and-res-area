"""
backend/tracker/motion.py

Background-subtraction-based motion detection using OpenCV MOG2.

The :class:`MotionDetector` exposes two methods:

* :meth:`~MotionDetector.detect` — returns a binary foreground mask.
* :meth:`~MotionDetector.has_motion` — convenience boolean test.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class MotionDetector:
    """Detects motion in a video stream using Gaussian Mixture background subtraction.

    Args:
        history:       Number of frames used to build the background model.
                       Higher values make the model slower to adapt.
        var_threshold: Mahalanobis distance threshold that determines whether a
                       pixel is classified as foreground.  Lower values increase
                       sensitivity.

    Example::

        detector = MotionDetector()
        cap = cv2.VideoCapture(0)
        while True:
            ret, frame = cap.read()
            if ret and detector.has_motion(frame):
                print("Motion detected!")
    """

    def __init__(self, history: int = 200, var_threshold: float = 40.0) -> None:
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=var_threshold,
            detectShadows=True,
        )
        # Morphological kernel for noise removal
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        logger.debug(
            "MotionDetector initialised (history=%d, var_threshold=%.1f).",
            history,
            var_threshold,
        )

    # ------------------------------------------------------------------ #

    def detect(self, frame: np.ndarray) -> np.ndarray:
        """Apply background subtraction and return a cleaned foreground mask.

        Shadow pixels (grey in the raw MOG2 mask) are mapped to background (0).
        The mask is cleaned with morphological opening to remove small noise
        and closing to fill holes.

        Args:
            frame: HxWx3 uint8 BGR image.

        Returns:
            Binary uint8 mask of the same spatial dimensions as *frame*
            (values 0 or 255).
        """
        raw_mask = self._subtractor.apply(frame)

        # Threshold: keep only definite foreground (255), discard shadows (127)
        _, fg_mask = cv2.threshold(raw_mask, 200, 255, cv2.THRESH_BINARY)

        # Remove noise (opening = erosion then dilation)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self._kernel)
        # Fill small holes (closing = dilation then erosion)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self._kernel)

        return fg_mask

    # ------------------------------------------------------------------ #

    def has_motion(self, frame: np.ndarray, min_area: int = 500) -> bool:
        """Return ``True`` if any foreground contour exceeds *min_area* pixels.

        Args:
            frame:    HxWx3 uint8 BGR image.
            min_area: Minimum contour area (in pixels²) to count as real motion.
                      Smaller contours are treated as noise.

        Returns:
            ``True`` when significant motion is detected, ``False`` otherwise.
        """
        mask = self.detect(frame)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            if cv2.contourArea(contour) >= min_area:
                logger.debug("Motion detected (contour area >= %d px²).", min_area)
                return True
        return False
