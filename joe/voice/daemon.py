from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

from ..config import Settings
from ..memory.store import MemoryStore
from ..personality.scaffold import Personality
from ..router import Router
from ..skills.base import SkillContext
from ..skills.registry import SkillRegistry
from ..state import JoeState
from ..llm.provider import OpenAICompatibleLLM
from ..camera.v4l2 import capture_frame, device_exists

from .alsa_stream import AlsaPCMStream, AlsaStreamConfig
from .vad_recorder import VadRecorder, VadRecorderConfig
from .stt_vosk import VoskSTT
from .tts import Speaker
from .wakeword import WakewordDetector

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceLoopStatus:
    ok: bool
    msg: str


class VoiceLoop:
    """MS4 demo-ready conversation loop.

    Wake: "Hey Joe" (via openWakeWord if available, otherwise via offline STT phrase detection)
    After wake: active listening for ~2-5 minutes, no repeated wakeword.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        hw = settings.hardware

        self.state = JoeState()
        self.memory = MemoryStore(str(settings.db_path))
        self.memory.init()

        self.registry = SkillRegistry.build_default(
            ssd_mount=hw.storage.ssd_mount,
        )
        self.router = Router(self.registry)

        self.personality = Personality(hw.personality)
        self.llm = OpenAICompatibleLLM(hw.llm)

        self.speaker = Speaker(
            output_device=hw.audio.output_device,
            piper_model_path=(hw.piper.model_path if hw.piper else None),
        )

        self.stream = AlsaPCMStream(
            AlsaStreamConfig(
                device=hw.audio.input_device,
                rate=hw.audio.input_rate,
                channels=hw.audio.input_channels,
            )
        )

        # Wakeword model (optional)
        model_path = hw.wakeword.model_path
        if not model_path:
            bundled = (settings.hardware_path.parent.parent / "wakeword" / "hey_joe.tflite")
            if bundled.exists() and bundled.stat().st_size > 0:
                model_path = str(bundled)
        self.wake = WakewordDetector(
            model_path=model_path,
            threshold=hw.wakeword.threshold,
            min_activation_frames=hw.wakeword.min_activation_frames,
            min_rms=hw.wakeword.min_rms,
        )

        self.vad = VadRecorder(
            VadRecorderConfig(
                aggressiveness=hw.vad.aggressiveness,
                silence_ms=hw.vad.silence_ms,
                max_record_ms=hw.vad.max_record_ms,
                sample_rate=hw.audio.input_rate,
            )
        )

        # Constrained grammar (optional) + ensure wake phrase included.
        grammar = hw.stt.grammar if hw.stt.mode in ("command", "auto") else None
        if grammar is not None:
            wake_phrase = (hw.conversation.wake_phrase or "Hey Joe").strip().lower()

            def _clean(tok: str) -> str | None:
                t = (tok or "").strip().lower()
                if not t:
                    return None
                if any(ch in t for ch in [",", ".", "!", "?", ";", ":"]):
                    return None
                if t in {"unmute", "heyjoe"}:
                    return None
                return t

            merged: list[str] = []
            for p in list(grammar) + [wake_phrase, "hey jo", "joe"]:
                c = _clean(p)
                if c and c not in merged:
                    merged.append(c)
            grammar = merged

        self.stt = VoskSTT(
            model_path=(hw.vosk.model_path if hw.vosk else ""),
            sample_rate=hw.audio.input_rate,
            grammar=grammar,
        )

        self.active_until: float = 0.0

    def _ctx(self) -> SkillContext:
        return SkillContext(source="voice", state=self.state, memory=self.memory)

    def _system_prompt(self) -> str:
        return (
            "You are Joe, a friendly offline assistant running on a Raspberry Pi. "
            "Respond briefly (1-2 sentences), be helpful, and do not claim to access the internet. "
            "If you don't know, say so plainly."
        )

    def _set_active_listen_window(self) -> None:
        conv = self.settings.hardware.conversation
        dur = random.randint(int(conv.active_listen_min_s), int(conv.active_listen_max_s))
        self.active_until = time.time() + dur

    def _in_conversation_mode(self) -> bool:
        return time.time() < self.active_until

    def _apply_alias(self, text: str) -> str:
        aliases = self.settings.hardware.stt.aliases or {}
        t = (text or "").strip().lower()
        for k, v in aliases.items():
            if t == (k or "").strip().lower():
                return v
        return text

    def init_camera_hooks(self) -> None:
        cam = self.settings.hardware.camera
        if not cam.enabled:
            log.info("Camera disabled in hardware.yaml — skipping init capture")
            return
        if not device_exists(cam.device):
            log.warning(
                "Camera device %s not present — no frame captured. "
                "MS4: running in no-camera mode until hardware is confirmed.",
                cam.device,
            )
            return
        try:
            result = capture_frame(cam.device, self.settings.data_dir / "camera")
            if result.ok:
                log.info("Camera init frame: %s", result.frame_path)
            else:
                log.warning("Camera init capture failed: %s", result.error)
        except Exception as exc:
            log.warning("Camera init unexpected error: %s", exc)

    def run_forever(self) -> VoiceLoopStatus:
        hw = self.settings.hardware

        import sys

        if not self.vad.ready():
            detail = getattr(self.vad, "error", lambda: None)()  # type: ignore
            hint = (
                "VAD not available. Install webrtcvad (requirements_voice.txt). "
                f"Details: {detail or 'unknown'}. "
                f"Python: {sys.executable}. "
                "If you are in a venv, ensure 'joe' comes from it and run: pip install -e ."
            )
            return VoiceLoopStatus(False, hint)

        if not self.stt.ready() or not (hw.vosk and hw.vosk.model_path):
            return VoiceLoopStatus(False, "STT not available. Install vosk + set vosk.model_path in hardware.yaml.")

        self.init_camera_hooks()

        self.stream.start()
        log.info(
            "VoiceLoop started — wake_phrase=%r ack=%r wakeword_model=%s "
            "stt_mode=%s ssd=%s",
            hw.conversation.wake_phrase,
            hw.conversation.wake_ack,
            "openWakeWord" if self.wake.ready() else "STT-fallback",
            hw.stt.mode,
            hw.storage.ssd_mount,
        )
        try:
            frame_bytes = int(hw.audio.input_rate * (hw.wakeword.frame_ms / 1000.0) * 2)  # int16

            while True:
                if not self._in_conversation_mode():
                    # Preferred: openWakeWord (low-latency)
                    if self.wake.ready():
                        pcm = self.stream.read(frame_bytes)
                        if not pcm:
                            continue
                        r = self.wake.process(pcm, sample_rate=hw.audio.input_rate)
                        if r.triggered:
                            self.speaker.speak(hw.conversation.wake_ack)
                            self._set_active_listen_window()
                        continue

                    # Fallback: STT-based wake phrase
                    utter_pcm = self.vad.record_one_utterance(self.stream)
                    if not utter_pcm:
                        continue
                    stt_res = self.stt.transcribe_pcm_s16le(utter_pcm)
                    if not stt_res.ok:
                        continue
                    text = (stt_res.text or "").strip().lower()
                    wake_phrase = (hw.conversation.wake_phrase or "hey joe").strip().lower()
                    if wake_phrase and wake_phrase in text:
                        self.speaker.speak(hw.conversation.wake_ack)
                        self._set_active_listen_window()
                    continue

                # Conversation mode
                utter_pcm = self.vad.record_one_utterance(self.stream)
                if not utter_pcm:
                    continue

                stt_res = self.stt.transcribe_pcm_s16le(utter_pcm)
                if not stt_res.ok:
                    self.speaker.speak(self.personality.wrap("Sorry, I didn't catch that."))
                    continue

                text = self._apply_alias(stt_res.text).strip()
                if not text:
                    continue

                if text.strip().lower() in ("stop", "cancel"):
                    self.active_until = 0
                    self.speaker.speak(self.personality.wrap("Okay."))
                    continue

                ctx = self._ctx()

                # 1) Local skills
                skill_res = self.router.match_skill(text, ctx)
                if skill_res is not None and skill_res.ok:
                    self.speaker.speak(self.personality.wrap(skill_res.text))
                    continue

                # 2) LLM fallback
                llm_res = self.llm.generate(user_text=text, system_prompt=self._system_prompt())
                if llm_res.ok and llm_res.text:
                    self.memory.add_event("voice", text, intent="llm:fallback", success=True, meta={})
                    self.speaker.speak(self.personality.wrap(llm_res.text))
                else:
                    self.memory.add_event(
                        "voice",
                        text,
                        intent="llm:fallback",
                        success=False,
                        meta={"error": llm_res.error or ""},
                    )
                    self.speaker.speak(self.personality.wrap("I can help with time, status, or volume."))

        except KeyboardInterrupt:
            return VoiceLoopStatus(True, "Stopped.")
        finally:
            try:
                self.stream.stop()
            except Exception:
                pass
            try:
                self.memory.close()
            except Exception:
                pass
