# 🔒 CV-Sentinel

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green)

**CV-Sentinel** is a standalone Computer Vision security application that performs real-time intrusion detection and restricted-area monitoring using a lightweight ONNX object-detection model (YOLOX-Nano). Detections are streamed to a React dashboard via WebSocket, giving security operators live situational awareness without any cloud dependency.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CV-Sentinel                                  │
│                                                                      │
│  ┌─────────────┐   frames    ┌──────────────────────────────────┐   │
│  │  Video      │ ──────────▶ │  Detection Pipeline              │   │
│  │  Source     │             │  ┌────────────┐ ┌─────────────┐ │   │
│  │  (cam/file) │             │  │ YOLOX-Nano │ │  ByteTrack  │ │   │
│  └─────────────┘             │  │  (ONNX RT) │ │  Tracker    │ │   │
│                              │  └─────┬──────┘ └──────┬──────┘ │   │
│                              │        │  tracks        │        │   │
│                              │  ┌─────▼────────────────▼──┐    │   │
│                              │  │      Use-Case Layer       │    │   │
│                              │  │  ┌───────────────────┐   │    │   │
│                              │  │  │ IntrusionDetector  │   │    │   │
│                              │  │  │ (armed hrs+cooldown│   │    │   │
│                              │  │  └───────────────────┘   │    │   │
│                              │  │  ┌───────────────────┐   │    │   │
│                              │  │  │RestrictedAreaMonitor   │    │   │
│                              │  │  │ (polygon+loitering)│   │    │   │
│                              │  │  └───────────────────┘   │    │   │
│                              │  └──────────┬────────────────┘    │   │
│                              └─────────────│────────────────────┘   │
│                                            │ alerts + annotated frame│
│  ┌─────────────────────────────────────────▼──────────────────────┐ │
│  │               FastAPI Backend  (uvicorn)                        │ │
│  │   REST /api/*          WebSocket /ws/stream                     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                            │                         │
│  ┌─────────────────────────────────────────▼──────────────────────┐ │
│  │               React 18 Dashboard  (Vite)                        │ │
│  │   Live video canvas · Alert feed · Zone config panel            │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Features

| Feature | Description |
|---|---|
| **Intrusion Detection** | Raises alerts when a person is detected during configurable armed hours (e.g. 22:00–06:00). Per-track cooldown prevents duplicate alert spam. |
| **Restricted Area Monitoring** | Define arbitrary convex/concave polygon zones. Alerts fire after a track's bottom-center dwell time exceeds the loiter threshold. Timer resets on exit. |
| **Live WebSocket Stream** | Annotated JPEG frames + alert JSON pushed to all connected clients at up to 30 fps. |
| **React Dashboard** | Real-time video canvas, alert timeline, zone configuration, and connection status — no page refresh required. |
| **Offline / Edge-Friendly** | All inference runs locally via ONNX Runtime (CPU). No cloud calls, no GPU required. |

---

## Prerequisites

| Dependency | Minimum Version | Notes |
|---|---|---|
| Python | 3.11 | `python --version` |
| pip | 23+ | bundled with Python |
| Node.js | 18 LTS | `node --version` |
| npm | 9+ | bundled with Node |
| Camera / video file | — | Webcam index `0` or any path OpenCV can read |

> [!NOTE]
> ONNX Runtime CPU is used by default. If you have an NVIDIA GPU, replace `onnxruntime` with `onnxruntime-gpu` in `backend/requirements.txt` for faster inference.

---

## Setup

### 1 — Clone / open workspace

```bash
git clone <repo-url> cv-sentinel
cd cv-sentinel
```

### 2 — Backend

```bash
cd backend
pip install -r requirements.txt
python download_models.py        # downloads yolox_nano.onnx (~3 MB)
```

Copy the example environment file and edit as needed:

```bash
cp .env.example .env
```

### 3 — Frontend

```bash
cd frontend
npm install
```

---

## Running

Open **two terminal windows** from the project root:

**Terminal 1 — Backend (API + inference loop)**

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend (dev server with HMR)**

```bash
cd frontend
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173) in your browser.

> [!TIP]
> Pass `--port` to `uvicorn` and update `VITE_API_URL` in `frontend/.env` if you need a different port.

---

## Configuration

All backend settings are read from environment variables (or a `.env` file in the `backend/` directory via `python-dotenv`).

| Variable | Default | Description |
|---|---|---|
| `VIDEO_SOURCE` | `0` | Webcam index **or** absolute path to a video file |
| `MODEL_PATH` | `backend/models/yolox_nano.onnx` | Path to the ONNX detection model |
| `CONFIDENCE_THRESHOLD` | `0.35` | Minimum detection confidence (0–1) |
| `ARMED_HOURS_START` | `22` | Hour (24 h) when intrusion detection arms |
| `ARMED_HOURS_END` | `6` | Hour (24 h) when intrusion detection disarms |
| `LOITER_SECONDS` | `5` | Seconds a track must dwell in a zone to trigger an alert |
| `HOST` | `0.0.0.0` | Uvicorn bind host |
| `PORT` | `8000` | Uvicorn bind port |

---

## API Reference

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Returns `{"status": "ok"}` |
| `GET` | `/api/alerts` | Last 100 alerts (JSON array) |
| `GET` | `/api/zones` | Current restricted-area zone definitions |
| `POST` | `/api/zones` | Replace zone list (body: array of zone objects) |
| `DELETE` | `/api/alerts` | Clear the in-memory alert buffer |

### WebSocket — `/ws/stream`

Connect with any WebSocket client. Each message is a JSON object:

```jsonc
{
  "frame": "<base64-encoded JPEG>",          // annotated video frame
  "tracks": [                                // active tracks this frame
    { "track_id": 7, "class": "person", "bbox": [x1, y1, x2, y2], "confidence": 0.87 }
  ],
  "alerts": [                                // alerts fired this frame (may be empty)
    {
      "type": "intrusion",                   // "intrusion" | "loitering"
      "track_id": 7,
      "timestamp": "2024-06-15T23:01:05",
      "zone_name": null                      // populated for loitering alerts
    }
  ],
  "fps": 24.3,
  "timestamp": "2024-06-15T23:01:05.123456"
}
```

---

## Testing

```bash
pytest tests/ -v
```

The test suite covers:

- `tests/test_intrusion.py` — `IntrusionDetector`: armed-hours logic, cooldown, class filtering, multiple tracks
- `tests/test_restricted_area.py` — `RestrictedAreaMonitor`: polygon containment, bottom-center calculation, loiter threshold, zone exit/reset

All tests use `unittest.mock.patch` for deterministic datetime control — no real-time waiting.

---

## Folder Structure

```
cv-sentinel/
├── backend/
│   ├── .env.example            # environment variable template
│   ├── requirements.txt        # Python dependencies
│   ├── main.py                 # FastAPI app + uvicorn entry point
│   ├── config.py               # Settings loaded from .env
│   ├── download_models.py      # One-shot model downloader
│   ├── models/                 # ONNX model weights (git-ignored)
│   │   └── yolox_nano.onnx
│   ├── core/
│   │   ├── __init__.py
│   │   ├── detector.py         # YOLOX-Nano ONNX inference wrapper
│   │   ├── tracker.py          # ByteTrack multi-object tracker
│   │   └── pipeline.py         # Orchestrates detect → track → use-cases
│   ├── usecases/
│   │   ├── __init__.py
│   │   ├── intrusion.py        # IntrusionDetector
│   │   └── restricted_area.py  # RestrictedAreaMonitor
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py           # REST route handlers
│   │   └── websocket.py        # WebSocket connection manager
│   └── schemas.py              # Pydantic request/response models
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       └── components/
│           ├── VideoCanvas.tsx
│           ├── AlertFeed.tsx
│           └── ZoneEditor.tsx
├── tests/
│   ├── __init__.py
│   ├── test_intrusion.py
│   └── test_restricted_area.py
├── .gitignore
└── README.md
```

---

## License

MIT © CV-Sentinel Contributors
