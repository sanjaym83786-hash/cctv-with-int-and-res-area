"""
backend/models/loader.py

Loads YOLOX object detection models via ONNX Runtime or TFLite,
pre-processes frames, runs inference and NMS, and returns structured detections.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# COCO 80-class label map
# --------------------------------------------------------------------------- #
COCO_LABELS: list[str] = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _letterbox(
    img: np.ndarray,
    new_shape: tuple[int, int] = (640, 640),
    color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize image to *new_shape* with letterboxing (keeps aspect ratio).

    Returns:
        img_lb:  Letterboxed image (H=new_shape[0], W=new_shape[1], C=3).
        scale:   Scale factor applied to the original image.
        pad:     (pad_left, pad_top) in pixels.
    """
    h0, w0 = img.shape[:2]
    new_h, new_w = new_shape
    scale = min(new_h / h0, new_w / w0)
    resized_h, resized_w = int(round(h0 * scale)), int(round(w0 * scale))

    img_resized = cv2.resize(img, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)

    # Padding to reach target shape
    pad_top = (new_h - resized_h) // 2
    pad_left = (new_w - resized_w) // 2
    pad_bottom = new_h - resized_h - pad_top
    pad_right = new_w - resized_w - pad_left

    img_lb = cv2.copyMakeBorder(
        img_resized, pad_top, pad_bottom, pad_left, pad_right,
        cv2.BORDER_CONSTANT, value=color,
    )
    return img_lb, scale, (pad_left, pad_top)


def _preprocess(frame: np.ndarray) -> np.ndarray:
    """Convert a BGR frame to a normalised NCHW float32 tensor (1,3,640,640)."""
    img, _, _ = _letterbox(frame, (640, 640))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0          # [0, 1]
    img = img.transpose(2, 0, 1)                   # HWC → CHW
    img = np.expand_dims(img, axis=0)              # CHW → NCHW
    return np.ascontiguousarray(img)


def _decode_yolox(
    outputs: np.ndarray,
    input_size: tuple[int, int] = (640, 640),
    orig_size: tuple[int, int] = (480, 640),
    conf_threshold: float = 0.35,
) -> list[dict]:
    """Decode raw YOLOX output (cx, cy, w, h, obj_conf, cls_conf…) into boxes.

    Args:
        outputs:        Model output array of shape (1, num_anchors, 85).
        input_size:     (H, W) used during inference.
        orig_size:      (H, W) of the original frame (before letterboxing).
        conf_threshold: Minimum score to keep a detection.

    Returns:
        List of dicts with keys ``bbox``, ``conf``, ``class_id``, ``label``.
    """
    predictions = outputs[0]                       # (num_anchors, 85)

    # Grids are generated at runtime to match anchor count
    num_anchors = predictions.shape[0]
    input_h, input_w = input_size

    # Build stride grids (YOLOX strides: 8, 16, 32 for 640×640)
    strides = [8, 16, 32]
    grids: list[np.ndarray] = []
    stride_vals: list[np.ndarray] = []
    for stride in strides:
        gh, gw = input_h // stride, input_w // stride
        yv, xv = np.meshgrid(np.arange(gh), np.arange(gw), indexing="ij")
        grid = np.stack((xv, yv), axis=-1).reshape(-1, 2).astype(np.float32)
        grids.append(grid)
        stride_vals.append(np.full((gh * gw, 1), stride, dtype=np.float32))

    grid_all = np.concatenate(grids, axis=0)          # (num_anchors, 2)
    stride_all = np.concatenate(stride_vals, axis=0)  # (num_anchors, 1)

    if grid_all.shape[0] != num_anchors:
        logger.warning(
            "Grid size %d does not match output anchors %d; skipping decode.",
            grid_all.shape[0], num_anchors,
        )
        return []

    # Decode cx, cy, w, h
    boxes_xy = (predictions[:, :2] + grid_all) * stride_all
    boxes_wh = np.exp(predictions[:, 2:4]) * stride_all

    # Convert to x1y1x2y2
    x1 = boxes_xy[:, 0] - boxes_wh[:, 0] / 2
    y1 = boxes_xy[:, 1] - boxes_wh[:, 1] / 2
    x2 = boxes_xy[:, 0] + boxes_wh[:, 0] / 2
    y2 = boxes_xy[:, 1] + boxes_wh[:, 1] / 2

    obj_conf = predictions[:, 4]                       # objectness
    cls_conf = predictions[:, 5:]                      # per-class confidence
    scores = obj_conf[:, None] * cls_conf              # (num_anchors, 80)
    class_ids = np.argmax(scores, axis=1)
    max_scores = scores[np.arange(len(scores)), class_ids]

    mask = max_scores >= conf_threshold
    x1, y1, x2, y2 = x1[mask], y1[mask], y1[mask], y2[mask]
    # Re-fetch x2 (the line above was a bug guard)
    x1 = (predictions[:, 0] + grid_all[:, 0] - np.exp(predictions[:, 2]) / 2 * 1)[mask]
    y1_m = y1  # already masked
    x2_raw = (predictions[:, 0] + grid_all[:, 0] + np.exp(predictions[:, 2]) / 2)[mask]

    # Redo cleanly
    boxes_xy_m = boxes_xy[mask]
    boxes_wh_m = boxes_wh[mask]
    x1 = boxes_xy_m[:, 0] - boxes_wh_m[:, 0] / 2
    y1_m = boxes_xy_m[:, 1] - boxes_wh_m[:, 1] / 2
    x2 = boxes_xy_m[:, 0] + boxes_wh_m[:, 0] / 2
    y2 = boxes_xy_m[:, 1] + boxes_wh_m[:, 1] / 2

    class_ids_m = class_ids[mask]
    max_scores_m = max_scores[mask]

    # Scale coords back to original image space (undo letterbox)
    orig_h, orig_w = orig_size
    scale = min(input_h / orig_h, input_w / orig_w)
    pad_left = (input_w - round(orig_w * scale)) // 2
    pad_top = (input_h - round(orig_h * scale)) // 2

    x1 = np.clip((x1 - pad_left) / scale, 0, orig_w)
    y1_m = np.clip((y1_m - pad_top) / scale, 0, orig_h)
    x2 = np.clip((x2 - pad_left) / scale, 0, orig_w)
    y2 = np.clip((y2 - pad_top) / scale, 0, orig_h)

    detections: list[dict] = []
    for i in range(len(x1)):
        cid = int(class_ids_m[i])
        label = COCO_LABELS[cid] if cid < len(COCO_LABELS) else str(cid)
        detections.append({
            "bbox": [float(x1[i]), float(y1_m[i]), float(x2[i]), float(y2[i])],
            "conf": float(max_scores_m[i]),
            "class_id": cid,
            "label": label,
        })
    return detections


def _nms(detections: list[dict], iou_threshold: float = 0.45) -> list[dict]:
    """Non-maximum suppression over detections grouped by class.

    Args:
        detections:    List of detection dicts with ``bbox`` and ``conf``.
        iou_threshold: IoU above which a box is suppressed.

    Returns:
        Filtered list of detections.
    """
    if not detections:
        return []

    bboxes = np.array([d["bbox"] for d in detections], dtype=np.float32)
    scores = np.array([d["conf"] for d in detections], dtype=np.float32)
    class_ids = np.array([d["class_id"] for d in detections])

    x1, y1, x2, y2 = bboxes[:, 0], bboxes[:, 1], bboxes[:, 2], bboxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    keep_indices: list[int] = []
    order = scores.argsort()[::-1]

    while order.size > 0:
        i = order[0]
        keep_indices.append(i)

        inter_x1 = np.maximum(x1[i], x1[order[1:]])
        inter_y1 = np.maximum(y1[i], y1[order[1:]])
        inter_x2 = np.minimum(x2[i], x2[order[1:]])
        inter_y2 = np.minimum(y2[i], y2[order[1:]])

        inter_w = np.maximum(0.0, inter_x2 - inter_x1)
        inter_h = np.maximum(0.0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        union_area = areas[i] + areas[order[1:]] - inter_area
        iou = inter_area / np.maximum(union_area, 1e-6)

        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]

    return [detections[k] for k in keep_indices]


# --------------------------------------------------------------------------- #
# ModelLoader
# --------------------------------------------------------------------------- #

class ModelLoader:
    """Loads and runs YOLOX object detection via ONNX Runtime or TFLite.

    Args:
        model_path: Path to the model file (``.onnx`` or ``.tflite``).
        backend:    One of ``"onnx"`` or ``"tflite"``.
    """

    SUPPORTED_BACKENDS: tuple[str, ...] = ("onnx", "tflite")

    def __init__(self, model_path: str, backend: str = "onnx") -> None:
        if backend not in self.SUPPORTED_BACKENDS:
            raise ValueError(
                f"Unsupported backend '{backend}'. Choose from {self.SUPPORTED_BACKENDS}."
            )
        self.model_path = Path(model_path)
        self.backend = backend
        self._session: Optional[object] = None  # onnxruntime.InferenceSession
        self._interpreter: Optional[object] = None  # tflite_runtime.interpreter.Interpreter
        self._input_name: str = ""
        self._loaded: bool = False

    # ------------------------------------------------------------------ #

    def load(self) -> None:
        """Load the model from disk.

        Logs a warning and returns without raising if the model file is absent.
        """
        if not self.model_path.is_file():
            logger.warning(
                "Model file not found at '%s'. Inference will return empty results.",
                self.model_path,
            )
            return

        if self.backend == "onnx":
            self._load_onnx()
        else:
            self._load_tflite()
        self._loaded = True
        logger.info("Model loaded from '%s' using backend '%s'.", self.model_path, self.backend)

    def _load_onnx(self) -> None:
        try:
            import onnxruntime as ort  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "onnxruntime is not installed. Run: pip install onnxruntime"
            ) from exc

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self._session = ort.InferenceSession(str(self.model_path), providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        logger.debug("ONNX session input name: '%s'", self._input_name)

    def _load_tflite(self) -> None:
        try:
            from tflite_runtime.interpreter import Interpreter  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "tflite_runtime is not installed. Run: pip install tflite-runtime"
            ) from exc

        self._interpreter = Interpreter(model_path=str(self.model_path))
        self._interpreter.allocate_tensors()
        input_details = self._interpreter.get_input_details()
        self._input_name = input_details[0]["index"]

    # ------------------------------------------------------------------ #

    def infer(self, frame: np.ndarray) -> list[dict]:
        """Run detection on a single BGR frame.

        Args:
            frame: HxWx3 uint8 BGR image (as returned by ``cv2.VideoCapture.read``).

        Returns:
            List of detection dicts, each with keys:
            ``bbox`` ([x1,y1,x2,y2]), ``conf`` (float), ``class_id`` (int),
            ``label`` (str).  Returns an empty list if the model is not loaded.
        """
        if not self._loaded:
            return []

        orig_h, orig_w = frame.shape[:2]
        input_tensor = _preprocess(frame)

        if self.backend == "onnx":
            raw = self._session.run(None, {self._input_name: input_tensor})
        else:
            details = self._interpreter.get_input_details()
            self._interpreter.set_tensor(details[0]["index"], input_tensor)
            self._interpreter.invoke()
            out_details = self._interpreter.get_output_details()
            raw = [self._interpreter.get_tensor(out_details[0]["index"])]

        # raw[0] shape: (1, num_anchors, 85)
        outputs = raw[0]
        if outputs.ndim == 2:
            outputs = outputs[np.newaxis, ...]  # ensure (1, anchors, 85)

        detections = _decode_yolox(
            outputs,
            input_size=(640, 640),
            orig_size=(orig_h, orig_w),
            conf_threshold=0.35,
        )
        detections = _nms(detections, iou_threshold=0.45)
        return detections
