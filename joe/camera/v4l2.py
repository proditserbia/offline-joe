from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time


@dataclass
class CameraStatus:
    ok: bool
    device: str
    frame_path: str | None = None
    error: str | None = None


def device_exists(device: str) -> bool:
    return Path(device).exists()


def capture_frame(device: str, out_dir: Path) -> CameraStatus:
    """Capture a single JPG frame from a V4L2 device using ffmpeg.

    This is intentionally lightweight: basic init + frame grab.
    """
    if not device_exists(device):
        return CameraStatus(False, device=device, error=f"Device not found: {device}")

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_path = out_dir / f"frame_{ts}.jpg"

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "v4l2",
        "-i",
        device,
        "-frames:v",
        "1",
        str(out_path),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return CameraStatus(True, device=device, frame_path=str(out_path))
    except Exception as e:
        return CameraStatus(False, device=device, error=str(e))
