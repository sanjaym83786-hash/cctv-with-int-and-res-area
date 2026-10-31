"""
backend/main.py

FastAPI application for the Computer Vision security backend.

Provides:
* REST endpoints for health-check, configuration, event log, and stats.
* A WebSocket endpoint that streams annotated video frames with real-time
  detection, tracking, and security-use-case alerts.

Environment variables (with defaults)::

    VIDEO_SOURCE=0                          # OpenCV capture index or RTSP URL
    MODEL_PATH=backend/models/yolox_nano.onnx
    CONFIDENCE_THRESHOLD=0.35
    ARMED_HOURS_START=22
    ARMED_HOURS_END=6
    LOITER_SECONDS=5

Run::

    uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import base64
import collections
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models.loader import ModelLoader
from tracker.motion import MotionDetector
from tracker.tracker import ByteTracker
from usecases.intrusion import IntrusionDetector
from usecases.restricted_area import RestrictedAreaMonitor

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configuration from environment variables
# --------------------------------------------------------------------------- #

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


_RAW_VIDEO_SOURCE = _env("VIDEO_SOURCE", "0")
try:
    VIDEO_SOURCE: int | str = int(_RAW_VIDEO_SOURCE)
except ValueError:
    VIDEO_SOURCE = _RAW_VIDEO_SOURCE

MODEL_PATH: str = _env("MODEL_PATH", "backend/models/yolox_nano.onnx")
CONFIDENCE_THRESHOLD: float = float(_env("CONFIDENCE_THRESHOLD", "0.35"))
# Default 0 to 24 (24/7 armed) so any person captured triggers intrusion detection immediately
ARMED_HOURS_START: int = int(_env("ARMED_HOURS_START", "0"))
ARMED_HOURS_END: int = int(_env("ARMED_HOURS_END", "24"))
ARMED_MODE: bool = _env("ARMED_MODE", "true").lower() in ("true", "1", "yes")
LOITER_SECONDS: float = float(_env("LOITER_SECONDS", "3"))

# --------------------------------------------------------------------------- #
# Application state container
# --------------------------------------------------------------------------- #


class AppState:
    """Mutable application state shared across request handlers."""

    def __init__(self) -> None:
        self.model: ModelLoader | None = None
        self.tracker: ByteTracker | None = None
        self.motion: MotionDetector | None = None
        self.intrusion: IntrusionDetector | None = None
        self.restricted: RestrictedAreaMonitor | None = None
        self.zones: list[dict] = [
            {
                "name": "Default Zone",
                "polygon": [[0, 0], [640, 0], [640, 480], [0, 480]],
                "loiter_seconds": LOITER_SECONDS,
            }
        ]
        self.event_log: collections.deque[dict] = collections.deque(maxlen=100)
        self.start_time: float = time.monotonic()
        self.total_alerts: int = 0
        self.frame_count: int = 0
        self.fps: float = 0.0


state = AppState()

# --------------------------------------------------------------------------- #
# Lifespan (startup / shutdown)
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    """Initialise all pipeline components at startup and clean up on shutdown."""
    logger.info("Initialising pipeline components …")

    state.model = ModelLoader(model_path=MODEL_PATH, backend="onnx")
    state.model.load()

    state.tracker = ByteTracker(max_age=30, min_hits=3, iou_threshold=0.3)
    state.motion = MotionDetector(history=200, var_threshold=40.0)
    state.intrusion = IntrusionDetector(
        {
            "armed_hours": (ARMED_HOURS_START, ARMED_HOURS_END),
            "cooldown_seconds": 10,
            "target_classes": ["person"],
            "enabled": ARMED_MODE,
        }
    )
    state.restricted = RestrictedAreaMonitor({"zones": state.zones})

    logger.info("All components initialised. Backend ready.")
    yield
    logger.info("Backend shutting down.")


# --------------------------------------------------------------------------- #
# FastAPI app
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="CV Security Backend",
    version="1.0.0",
    description="Real-time Computer Vision security pipeline with intrusion and restricted-area detection.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# Pydantic models
# --------------------------------------------------------------------------- #


class ArmConfigRequest(BaseModel):
    """Request body for arming/disarming intrusion detection."""
    armed: bool
    armed_hours_start: list[int] | None = None
    armed_hours_end: list[int] | None = None
    cooldown_seconds: float | None = None


class ZoneVertex(BaseModel):
    """A single 2-D vertex of a zone polygon."""
    x: float
    y: float


class ZoneDefinition(BaseModel):
    """Definition of a restricted zone."""
    name: str
    polygon: list[list[float]]
    loiter_seconds: float = 5.0


class ZonesUpdateRequest(BaseModel):
    """Request body for ``POST /config/zones``."""
    zones: list[ZoneDefinition]


# --------------------------------------------------------------------------- #
# REST endpoints
# --------------------------------------------------------------------------- #


@app.get("/health", summary="Health check")
async def health() -> dict[str, Any]:
    """Return service liveness status and current UTC timestamp."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.get("/config", summary="Get current configuration")
async def get_config() -> dict[str, Any]:
    """Return the active runtime configuration."""
    is_armed = state.intrusion.enabled if state.intrusion else True
    return {
        "video_source": VIDEO_SOURCE,
        "model_path": MODEL_PATH,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "armed": is_armed,
        "armed_hours_start": state.intrusion.armed_start if state.intrusion else ARMED_HOURS_START,
        "armed_hours_end": state.intrusion.armed_end if state.intrusion else ARMED_HOURS_END,
        "cooldown_seconds": state.intrusion.cooldown_seconds if state.intrusion else 10,
        "loiter_seconds": LOITER_SECONDS,
        "zones": state.zones,
    }


@app.post("/config/arm", summary="Configure intrusion detection arming")
async def set_arm_config(body: ArmConfigRequest) -> dict[str, Any]:
    """Update armed state, hours, or cooldown."""
    if state.intrusion:
        state.intrusion.enabled = body.armed
        if body.armed_hours_start is not None and body.armed_hours_end is not None:
            state.intrusion.armed_start = body.armed_hours_start
            state.intrusion.armed_end = body.armed_hours_end
        if body.cooldown_seconds is not None:
            state.intrusion.cooldown_seconds = body.cooldown_seconds
    return {
        "status": "updated",
        "armed": state.intrusion.enabled if state.intrusion else body.armed,
        "armed_hours": (state.intrusion.armed_start, state.intrusion.armed_end) if state.intrusion else (0, 24),
    }


@app.post("/config/zones", summary="Update zone polygons")
async def update_zones(body: ZonesUpdateRequest) -> dict[str, Any]:
    """Replace the set of restricted zones and reinitialise the monitor.

    Args:
        body: JSON body containing a list of zone definitions.

    Returns:
        Confirmation with the updated zones list.
    """
    new_zones = [z.model_dump() for z in body.zones]
    state.zones = new_zones
    # Reinitialise the restricted-area monitor with the new zones
    state.restricted = RestrictedAreaMonitor({"zones": new_zones})
    logger.info("Zones updated: %s", [z["name"] for z in new_zones])
    return {"status": "updated", "zones": new_zones}


@app.get("/api/events", summary="Retrieve recent events")
async def get_events() -> dict[str, Any]:
    """Return the last 100 security events stored in the in-memory log."""
    return {"events": list(state.event_log), "count": len(state.event_log)}


@app.get("/api/stats", summary="Runtime statistics")
async def get_stats() -> dict[str, Any]:
    """Return current FPS, total alert count, and server uptime."""
    uptime = time.monotonic() - state.start_time
    return {
        "fps": round(state.fps, 2),
        "frame_count": state.frame_count,
        "total_alerts": state.total_alerts,
        "uptime_seconds": round(uptime, 1),
    }


# --------------------------------------------------------------------------- #
# Annotation helpers
# --------------------------------------------------------------------------- #

# Colour constants (BGR)
_COLOUR_PERSON = (0, 220, 0)      # green
_COLOUR_ALERT = (0, 0, 220)       # red
_COLOUR_OTHER = (220, 165, 0)     # orange
_COLOUR_ZONE = (220, 220, 0)      # yellow
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _draw_tracks(frame: np.ndarray, tracks: list[dict], alert_ids: set[int]) -> None:
    """Draw bounding boxes and track labels on *frame* in-place.

    Persons with active alerts are drawn in red; persons without are green;
    all other classes are orange.
    """
    for track in tracks:
        tid = track["track_id"]
        x1, y1, x2, y2 = (int(v) for v in track["bbox"])
        label = track.get("label", "?")

        if tid in alert_ids:
            colour = _COLOUR_ALERT
        elif label == "person":
            colour = _COLOUR_PERSON
        else:
            colour = _COLOUR_OTHER

        cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)
        text = f"{label} #{tid} {track.get('conf', 0):.2f}"
        (tw, th), _ = cv2.getTextSize(text, _FONT, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw, y1), colour, -1)
        cv2.putText(frame, text, (x1, y1 - 4), _FONT, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def _draw_zones(frame: np.ndarray, zones: list[dict]) -> None:
    """Draw zone polygon outlines on *frame* in-place."""
    for zone in zones:
        pts = np.array(zone["polygon"], dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [pts], isClosed=True, color=_COLOUR_ZONE, thickness=2)
        # Label at the first vertex
        if zone["polygon"]:
            vx, vy = int(zone["polygon"][0][0]), int(zone["polygon"][0][1])
            cv2.putText(
                frame, zone["name"], (vx + 4, vy + 16),
                _FONT, 0.5, _COLOUR_ZONE, 1, cv2.LINE_AA,
            )


def _encode_frame(frame: np.ndarray) -> str:
    """JPEG-encode *frame* and return a base-64 string."""
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf.tobytes()).decode("utf-8")


# --------------------------------------------------------------------------- #
# WebSocket stream
# --------------------------------------------------------------------------- #


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket) -> None:
    """Stream annotated video frames with detection, tracking, and alert data.

    Each message is a JSON object::

        {
            "frame":  "<base64-encoded JPEG>",
            "tracks": [ {track_id, bbox, conf, class_id, label}, … ],
            "alerts": [ {type, track_id, …}, … ],
            "stats":  {"fps": float, "frame_count": int},
        }

    The connection is closed gracefully when the client disconnects or when the
    video source cannot supply frames.
    """
    await websocket.accept()
    logger.info("WebSocket client connected from %s.", websocket.client)

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        logger.error("Cannot open video source '%s'.", VIDEO_SOURCE)
        await websocket.send_json({"error": f"Cannot open video source '{VIDEO_SOURCE}'."})
        await websocket.close()
        return

    fps_timer = time.monotonic()
    fps_frames = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Video source returned no frame; retrying …")
                await asyncio.sleep(0.05)
                continue

            frame_time = datetime.now()
            state.frame_count += 1
            fps_frames += 1

            # ── FPS calculation (rolling window over 1 s) ─────────────── #
            now = time.monotonic()
            elapsed = now - fps_timer
            if elapsed >= 1.0:
                state.fps = fps_frames / elapsed
                fps_frames = 0
                fps_timer = now

            # ── Motion gate (skip expensive inference if no motion) ────── #
            motion_present = state.motion.has_motion(frame, min_area=500)

            if motion_present:
                detections = state.model.infer(frame)
            else:
                detections = []

            # ── Tracking ──────────────────────────────────────────────── #
            tracks = state.tracker.update(detections)

            # ── Use-case processing ───────────────────────────────────── #
            intrusion_alerts = state.intrusion.process(tracks, frame_time)
            restricted_alerts = state.restricted.process(tracks, frame_time)
            all_alerts = intrusion_alerts + restricted_alerts

            # ── Log events ───────────────────────────────────────────── #
            for alert in all_alerts:
                state.event_log.append(alert)
                state.total_alerts += 1

            # ── Annotation ───────────────────────────────────────────── #
            alert_track_ids: set[int] = {a["track_id"] for a in all_alerts}
            _draw_zones(frame, state.zones)
            _draw_tracks(frame, tracks, alert_track_ids)

            # HUD overlay
            hud = (
                f"FPS: {state.fps:.1f}  |  Tracks: {len(tracks)}"
                f"  |  Alerts: {state.total_alerts}"
            )
            cv2.putText(frame, hud, (8, 24), _FONT, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

            # ── Encode and send ───────────────────────────────────────── #
            frame_b64 = await asyncio.get_event_loop().run_in_executor(
                None, _encode_frame, frame
            )

            payload = {
                "frame": frame_b64,
                "tracks": tracks,
                "alerts": all_alerts,
                "zones": state.zones,
                "stats": {
                    "fps": round(state.fps, 2),
                    "frame_count": state.frame_count,
                    "total_alerts": state.total_alerts,
                },
            }

            await websocket.send_text(json.dumps(payload))

            # Yield control so other coroutines can run
            await asyncio.sleep(0)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in WebSocket stream: %s", exc)
    finally:
        cap.release()
        logger.info("Video capture released.")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
