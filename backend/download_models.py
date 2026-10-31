"""
backend/download_models.py

Convenience script that downloads all required model weights for the
Computer Vision security application.

Usage::

    python -m backend.download_models
    # or
    python backend/download_models.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — run standalone or from the package root
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------
# Each entry: (display_name, url, relative_dest_path)
_MODELS: list[tuple[str, str, str]] = [
    (
        "YOLOX-Nano (ONNX)",
        "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx",
        "backend/models/yolox_nano.onnx",
    ),
]

# ---------------------------------------------------------------------------


def _resolve_project_root() -> Path:
    """Return the repository root (parent of the ``backend`` package dir)."""
    this_file = Path(__file__).resolve()
    # backend/download_models.py → project root is two levels up
    return this_file.parent.parent


def main() -> None:
    """Download all model files, skipping ones that already exist."""
    try:
        from backend.models.downloader import download_model  # noqa: PLC0415
    except ImportError:
        # Allow running as a plain script without package installation
        sys.path.insert(0, str(_resolve_project_root()))
        from backend.models.downloader import download_model  # type: ignore[no-redef]

    project_root = _resolve_project_root()
    failed: list[str] = []

    for display_name, url, rel_dest in _MODELS:
        dest = project_root / rel_dest
        logger.info("Preparing to download: %s", display_name)
        try:
            download_model(url, dest)
            logger.info("✓ %s ready at '%s'.", display_name, dest)
        except Exception as exc:  # noqa: BLE001
            logger.error("✗ Failed to download %s: %s", display_name, exc)
            failed.append(display_name)

    if failed:
        print("\n" + "=" * 70)
        print("The following models could not be downloaded automatically:")
        for name in failed:
            print(f"  • {name}")
        print("\nManual download instructions:")
        print("  1. Visit the YOLOX GitHub releases page:")
        print("     https://github.com/Megvii-BaseDetection/YOLOX/releases/tag/0.1.1rc0")
        print("  2. Download 'yolox_nano.onnx'.")
        print("  3. Place the file at:  backend/models/yolox_nano.onnx")
        print("=" * 70 + "\n")
        sys.exit(1)
    else:
        print("\nAll models downloaded successfully. You can now start the backend.")


if __name__ == "__main__":
    main()
