"""Audio diagnostics for Offline Joe."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioProbeResult:
    backend: str
    volume_percent: int | None
    arecord_ok: bool
    aplay_ok: bool
    detail: str | None = None


def probe_audio() -> AudioProbeResult:
    """Quick audio subsystem probe (no recording performed)."""
    from joe.audio.volume import detect_backend, get_volume_percent

    backend = detect_backend().kind
    volume = get_volume_percent()
    arecord_ok = shutil.which("arecord") is not None
    aplay_ok = shutil.which("aplay") is not None

    return AudioProbeResult(
        backend=backend,
        volume_percent=volume,
        arecord_ok=arecord_ok,
        aplay_ok=aplay_ok,
    )


def probe_alsa_devices() -> list[str]:
    """Return lines from ``aplay -l`` listing playback devices."""
    if not shutil.which("aplay"):
        return ["aplay not found"]
    try:
        cp = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return cp.stdout.strip().splitlines()
    except Exception as exc:
        return [f"Error: {exc}"]
