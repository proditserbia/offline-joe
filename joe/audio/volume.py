from __future__ import annotations

import re
from dataclasses import dataclass

from ..utils.shell import has_cmd, run


@dataclass(frozen=True)
class VolumeBackend:
    kind: str  # "pactl" | "amixer" | "none"


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
        cp = run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], timeout_s=2)
        if cp.returncode != 0:
            return None
        m = re.search(r"(\d+)%", cp.stdout)
        return int(m.group(1)) if m else None

    if b.kind == "amixer":
        cp = run(["amixer", "get", "Master"], timeout_s=2)
        if cp.returncode != 0:
            return None
        m = re.search(r"\[(\d+)%\]", cp.stdout)
        return int(m.group(1)) if m else None

    return None


def set_volume_percent(value: int) -> bool:
    value = max(0, min(100, int(value)))
    b = detect_backend()
    if b.kind == "pactl":
        cp = run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"], timeout_s=2)
        return cp.returncode == 0
    if b.kind == "amixer":
        cp = run(["amixer", "set", "Master", f"{value}%"], timeout_s=2)
        return cp.returncode == 0
    return False


def mute(muted: bool) -> bool:
    b = detect_backend()
    if b.kind == "pactl":
        cp = run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"], timeout_s=2)
        return cp.returncode == 0
    if b.kind == "amixer":
        cp = run(["amixer", "set", "Master", "mute" if muted else "unmute"], timeout_s=2)
        return cp.returncode == 0
    return False
