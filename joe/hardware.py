from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def _req_str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    if v is None or str(v).strip() == "":
        raise ValueError(f"Missing required config key: {key}")
    return str(v)


@dataclass(frozen=True)
class WakewordConfig:
    model_path: str | None = None
    threshold: float = 0.4
    frame_ms: int = 80
    min_activation_frames: int = 3
    min_rms: int = 1000


@dataclass(frozen=True)
class VadConfig:
    aggressiveness: int = 2
    silence_ms: int = 800
    max_record_ms: int = 8000


@dataclass(frozen=True)
class AudioConfig:
    input_device: str
    output_device: str
    input_rate: int = 16000
    input_channels: int = 1
    record_seconds: int = 3


@dataclass(frozen=True)
class SttConfig:
    mode: str = "auto"  # free|command|auto
    grammar: list[str] | None = None
    aliases: dict[str, str] | None = None


@dataclass(frozen=True)
class VoskConfig:
    model_path: str


@dataclass(frozen=True)
class PiperConfig:
    model_path: str


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool = False
    base_url: str = "http://localhost:11434/v1"
    api_key: str | None = None
    model: str = "llama3"
    timeout_s: int = 20


@dataclass(frozen=True)
class PersonalityConfig:
    warmth: int = 2      # 0-3
    humor: int = 1       # 0-3
    directness: int = 2  # 0-3


@dataclass(frozen=True)
class ConversationConfig:
    active_listen_min_s: int = 120
    active_listen_max_s: int = 300
    wake_phrase: str = "Hey Joe"
    wake_ack: str = "Hi."


@dataclass(frozen=True)
class CameraConfig:
    enabled: bool = True
    device: str = "/dev/video0"
    backend: str = "v4l2"


@dataclass(frozen=True)
class HardwareConfig:
    audio: AudioConfig
    wakeword: WakewordConfig
    vad: VadConfig
    stt: SttConfig
    vosk: VoskConfig | None = None
    piper: PiperConfig | None = None
    llm: LlmConfig = LlmConfig()
    personality: PersonalityConfig = PersonalityConfig()
    conversation: ConversationConfig = ConversationConfig()
    camera: CameraConfig = CameraConfig()


def load_hardware_config(path: Path) -> HardwareConfig:
    """Load and validate hardware.yaml into strongly-typed dataclasses."""
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    audio_d = data.get("audio") or {}
    audio = AudioConfig(
        input_device=_req_str(audio_d, "input_device"),
        output_device=_req_str(audio_d, "output_device"),
        input_rate=int(audio_d.get("input_rate", 16000)),
        input_channels=int(audio_d.get("input_channels", 1)),
        record_seconds=int(audio_d.get("record_seconds", 3)),
    )

    wake_d = data.get("wakeword") or {}
    model_path = wake_d.get("model_path")
    if model_path is not None and str(model_path).strip() == "":
        model_path = None
    wakeword = WakewordConfig(
        model_path=model_path,
        threshold=float(wake_d.get("threshold", 0.4)),
        frame_ms=int(wake_d.get("frame_ms", 80)),
        min_activation_frames=int(wake_d.get("min_activation_frames", 3)),
        min_rms=int(wake_d.get("min_rms", 1000)),
    )

    vad_d = data.get("vad") or {}
    vad = VadConfig(
        aggressiveness=int(vad_d.get("aggressiveness", 2)),
        silence_ms=int(vad_d.get("silence_ms", 800)),
        max_record_ms=int(vad_d.get("max_record_ms", 8000)),
    )

    stt_d = data.get("stt") or {}
    stt = SttConfig(
        mode=str(stt_d.get("mode", "auto")).strip().lower(),
        grammar=list(stt_d.get("grammar") or []) or None,
        aliases=dict(stt_d.get("aliases") or {}) or None,
    )
    if stt.mode not in {"free", "command", "auto"}:
        raise ValueError(f"stt.mode must be one of free|command|auto, got: {stt.mode}")

    vosk_cfg = None
    vosk_d = data.get("vosk") or {}
    if vosk_d.get("model_path"):
        vosk_cfg = VoskConfig(model_path=str(vosk_d.get("model_path")))

    piper_cfg = None
    piper_d = data.get("piper") or {}
    if piper_d.get("model_path"):
        piper_cfg = PiperConfig(model_path=str(piper_d.get("model_path")))

    llm_d = data.get("llm") or {}
    llm = LlmConfig(
        enabled=bool(llm_d.get("enabled", False)),
        base_url=str(llm_d.get("base_url", "http://localhost:11434/v1")).strip(),
        api_key=llm_d.get("api_key"),
        model=str(llm_d.get("model", "llama3")).strip(),
        timeout_s=int(llm_d.get("timeout_s", 20)),
    )

    per_d = data.get("personality") or {}
    personality = PersonalityConfig(
        warmth=int(per_d.get("warmth", 2)),
        humor=int(per_d.get("humor", 1)),
        directness=int(per_d.get("directness", 2)),
    )

    conv_d = data.get("conversation") or {}
    conversation = ConversationConfig(
        active_listen_min_s=int(conv_d.get("active_listen_min_s", 120)),
        active_listen_max_s=int(conv_d.get("active_listen_max_s", 300)),
        wake_phrase=str(conv_d.get("wake_phrase", "Hey Joe")).strip(),
        wake_ack=str(conv_d.get("wake_ack", "Hi.")).strip(),
    )

    cam_d = data.get("camera") or {}
    camera = CameraConfig(
        enabled=bool(cam_d.get("enabled", True)),
        device=str(cam_d.get("device", "/dev/video0")).strip(),
        backend=str(cam_d.get("backend", "v4l2")).strip(),
    )

    return HardwareConfig(
        audio=audio,
        wakeword=wakeword,
        vad=vad,
        stt=stt,
        vosk=vosk_cfg,
        piper=piper_cfg,
        llm=llm,
        personality=personality,
        conversation=conversation,
        camera=camera,
    )
