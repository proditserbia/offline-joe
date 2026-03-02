from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
import time

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraStatus:
    ok: bool
    device: str
    frame_path: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class CameraProbeResult:
    """Result of a camera availability probe."""
    available: bool
    device: str
    method: str
    detail: str | None = None


def device_exists(device: str) -> bool:
    return Path(device).exists()


def probe_camera(device: str = "/dev/video0") -> CameraProbeResult:
    """Check whether a camera is actually accessible.

    Strategy (in order):
    1. Check that the ``/dev/videoX`` device node exists.
    2. If ``rpicam-hello`` is present, run ``rpicam-hello --list-cameras``
       and parse whether any cameras are reported.

    Returns a :class:`CameraProbeResult` describing the finding so callers
    can log or report appropriately instead of treating every absence as an
    unexpected error.
    """
    if not device_exists(device):
        log.warning(
            "Camera device not found: %s — "
            "check cable/ribbon and run 'rpicam-hello --list-cameras'",
            device,
        )
        return CameraProbeResult(
            available=False,
            device=device,
            method="device_node",
            detail=f"No device node at {device}",
        )

    # Device node is present; optionally confirm via rpicam-hello.
    if shutil.which("rpicam-hello"):
        try:
            cp = subprocess.run(
                ["rpicam-hello", "--list-cameras"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = (cp.stdout + cp.stderr).strip()
            if "No cameras available" in output or "no cameras" in output.lower():
                log.warning(
                    "rpicam-hello reports no cameras available "
                    "(ribbon seated? replacement ordered?): %s",
                    output[:200],
                )
                return CameraProbeResult(
                    available=False,
                    device=device,
                    method="rpicam-hello",
                    detail=output[:200],
                )
            log.debug("rpicam-hello output: %s", output[:200])
            return CameraProbeResult(
                available=True,
                device=device,
                method="rpicam-hello",
                detail=output[:200],
            )
        except Exception as exc:
            log.debug("rpicam-hello probe failed (non-fatal): %s", exc)

    # Device node exists and we could not run rpicam-hello; optimistically available.
    return CameraProbeResult(available=True, device=device, method="device_node")


def capture_frame(device: str, out_dir: Path) -> CameraStatus:
    """Capture a single JPG frame from a V4L2 device using ffmpeg.

    Returns a :class:`CameraStatus` with ``ok=False`` and a human-readable
    ``error`` message if the device is absent or capture fails — it never
    raises.
    """
    probe = probe_camera(device)
    if not probe.available:
        return CameraStatus(
            False,
            device=device,
            error=f"Camera not available: {probe.detail or probe.method}",
        )

    if not shutil.which("ffmpeg"):
        return CameraStatus(False, device=device, error="ffmpeg not found (sudo apt install ffmpeg)")

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
        log.info("Camera frame captured: %s", out_path)
        return CameraStatus(True, device=device, frame_path=str(out_path))
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode(errors="replace").strip()
        log.warning("ffmpeg capture failed on %s: %s", device, err)
        return CameraStatus(False, device=device, error=f"ffmpeg error: {err}")
    except Exception as e:
        log.warning("Camera capture error: %s", e)
        return CameraStatus(False, device=device, error=f"{type(e).__name__}: {e}")
