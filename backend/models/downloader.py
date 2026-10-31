"""
backend/models/downloader.py

Utility to download model files from remote URLs with a progress bar,
skipping re-downloads when the local file is already complete.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)


def download_model(url: str, dest: Path) -> None:
    """Download a model file from *url* to *dest*, showing a progress bar.

    The download is skipped when *dest* already exists **and** its size matches
    the ``Content-Length`` header reported by the server (i.e. the file is
    complete).  Partial files are always re-downloaded.

    Args:
        url:  Full HTTPS URL of the model artifact.
        dest: Local :class:`~pathlib.Path` where the file should be saved.
              Parent directories are created automatically.

    Raises:
        requests.HTTPError: If the server returns a non-2xx status code.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # HEAD request to get expected file size without downloading the body
    try:
        head = requests.head(url, allow_redirects=True, timeout=15)
        head.raise_for_status()
        remote_size = int(head.headers.get("Content-Length", -1))
    except requests.RequestException:
        # Fall through — we'll find out during GET if something is wrong
        remote_size = -1

    if dest.is_file() and remote_size > 0 and dest.stat().st_size == remote_size:
        logger.info(
            "Model already exists at '%s' (%d bytes). Skipping download.", dest, remote_size
        )
        return

    logger.info("Downloading model from '%s' → '%s' …", url, dest)

    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))

        with (
            open(dest, "wb") as fh,
            tqdm(
                total=total or None,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=dest.name,
                dynamic_ncols=True,
            ) as bar,
        ):
            for chunk in resp.iter_content(chunk_size=1 << 16):  # 64 KiB chunks
                fh.write(chunk)
                bar.update(len(chunk))

    logger.info("Download complete: '%s' (%d bytes).", dest, dest.stat().st_size)
