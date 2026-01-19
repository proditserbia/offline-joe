from __future__ import annotations
import re
from dataclasses import dataclass
from ..utils.shell import has_cmd, run

@dataclass
class VolumeBackend:
    kind: str  # "pactl" | "amixer"

def detect_backend() -> VolumeBackend:
    # PipeWire typically exposes pactl as well; PulseAudio same.
    if has_cmd("pactl"):
        return VolumeBackend("pactl")
    if has_cmd("amixer"):
        return VolumeBackend("amixer")
    return VolumeBackend("none")

def get_volume_percent() -> int | None:
    b = detect_backend()
    if b.kind == "pactl":
        # default sink volume (first %)
        cp = run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        if cp.returncode != 0:
            return None
        m = re.search(r"(\d+)%", cp.stdout)
        return int(m.group(1)) if m else None

    if b.kind == "amixer":
        cp = run(["amixer", "get", "Master"])
        if cp.returncode != 0:
            return None
        m = re.search(r"\[(\d+)%\]", cp.stdout)
        return int(m.group(1)) if m else None

    return None

def set_volume_percent(value: int) -> bool:
    value = max(0, min(100, int(value)))
    b = detect_backend()
    if b.kind == "pactl":
        cp = run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"])
        return cp.returncode == 0
    if b.kind == "amixer":
        cp = run(["amixer", "set", "Master", f"{value}%"])
        return cp.returncode == 0
    return False

def mute(muted: bool) -> bool:
    b = detect_backend()
    if b.kind == "pactl":
        cp = run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"])
        return cp.returncode == 0
    if b.kind == "amixer":
        cp = run(["amixer", "set", "Master", "mute" if muted else "unmute"])
        return cp.returncode == 0
    return False
