from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..config import Settings
from ..memory.store import MemoryStore
from ..skills.registry import SkillRegistry
from ..router import Router
from ..state import JoeState
from ..skills.base import SkillContext
from ..personality.scaffold import Personality
from ..llm.provider import OpenAICompatibleLLM
from ..camera.v4l2 import capture_frame, device_exists

from .alsa_stream import AlsaPCMStream, AlsaStreamConfig
from .wakeword import WakewordDetector
from .vad_recorder import VadRecorder, VadRecorderConfig
from .stt_vosk import VoskSTT
from .tts import Speaker


@dataclass
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

        self.registry = SkillRegistry.build_default()
        self.router = Router(self.registry)

        self.personality = Personality(hw.personality)
        self.llm = OpenAICompatibleLLM(hw.llm)

        self.speaker = Speaker(output_device=hw.audio.output_device,
                               piper_model_path=(hw.piper.model_path if hw.piper else None))

        self.stream = AlsaPCMStream(AlsaStreamConfig(
            device=hw.audio.input_device,
            rate=hw.audio.input_rate,
            channels=hw.audio.input_channels,
        ))

        model_path = hw.wakeword.model_path
        if not model_path:
            # default to bundled model if present
            bundled = (settings.hardware_path.parent.parent / "wakeword" / "hey_joe.tflite")
            if bundled.exists():
                model_path = str(bundled)
        self.wake = WakewordDetector(
            model_path=model_path,
            threshold=hw.wakeword.threshold,
            min_activation_frames=hw.wakeword.min_activation_frames,
            min_rms=hw.wakeword.min_rms,
        )

        self.vad = VadRecorder(VadRecorderConfig(
            aggressiveness=hw.vad.aggressiveness,
            silence_ms=hw.vad.silence_ms,
            max_record_ms=hw.vad.max_record_ms,
            sample_rate=hw.audio.input_rate,
        ))

        # Ensure wake phrase is included in constrained grammar modes.
        grammar = hw.stt.grammar if hw.stt.mode in ("command", "auto") else None
        if grammar is not None:
            wake_phrase = (hw.conversation.wake_phrase or "Hey Joe").strip().lower()
            extra = [wake_phrase, wake_phrase.replace(" ", ""), "hey, joe", "hey jo"]
            merged = list(grammar)
            for p in extra:
                p = (p or "").strip().lower()
                if p and p not in [x.strip().lower() for x in merged]:
                    merged.append(p)
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
        # MS4: deterministic, no tools, no memory. Just realism.
        return (
            "You are Joe, a friendly offline assistant running on a Raspberry Pi. "
            "Respond briefly (1-2 sentences), be helpful, and do not claim to access the internet. "
            "If you don't know, say so plainly."
        )

    def _set_active_listen_window(self):
        hw = self.settings.hardware.conversation
        dur = random.randint(hw.active_listen_min_s, hw.active_listen_max_s)
        self.active_until = time.time() + dur

    def _in_conversation_mode(self) -> bool:
        return time.time() < self.active_until

    def _apply_alias(self, text: str) -> str:
        aliases = self.settings.hardware.stt.aliases or {}
        t = (text or "").strip().lower()
        for k, v in aliases.items():
            if t == k.strip().lower():
                return v
        return text

    def init_camera_hooks(self) -> None:
        cam = self.settings.hardware.camera
        if not cam.enabled:
            return
        if not device_exists(cam.device):
            return
        # One basic frame capture for init validation (non-blocking)
        try:
            capture_frame(cam.device, self.settings.data_dir / "camera")
        except Exception:
            pass

    def run_forever(self) -> VoiceLoopStatus:
        hw = self.settings.hardware

        # Preconditions (soft failures to allow demo debugging)
        # Wakeword engine is OPTIONAL in MS4; we can fall back to STT-based wake phrase detection.
        if not self.vad.ready():
            return VoiceLoopStatus(False, "VAD not available. Install webrtcvad (requirements_voice.txt).")
        if not self.stt.ready() or not (hw.vosk and hw.vosk.model_path):
            return VoiceLoopStatus(False, "STT not available. Install vosk + set vosk.model_path in hardware.yaml.")

        self.init_camera_hooks()

        self.stream.start()
        try:
            # Wakeword loop
            frame_bytes = int(hw.audio.input_rate * (hw.wakeword.frame_ms / 1000.0) * 2)  # int16
            while True:
                if not self._in_conversation_mode():
                    # Preferred: openWakeWord (very low-latency)
                    if self.wake.ready():
                        pcm = self.stream.read(frame_bytes)
                        if not pcm:
                            continue
                        r = self.wake.process(pcm, sample_rate=hw.audio.input_rate)
                        if r.triggered:
                            # immediate spoken acknowledgement
                            self.speaker.speak(hw.conversation.wake_ack)
                            self._set_active_listen_window()
                        continue

                    # Fallback (MS4-safe): STT-based wake phrase "Hey Joe"
                    # This avoids platform-specific wakeword deps (e.g. tflite-runtime wheels on Py3.13).
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

                # Conversation mode: record utterance (VAD)
                utter_pcm = self.vad.record_one_utterance(self.stream)
                if not utter_pcm:
                    # If no speech, just keep listening until window expires
                    continue

                stt_res = self.stt.transcribe_pcm_s16le(utter_pcm)
                if not stt_res.ok:
                    self.speaker.speak(self.personality.wrap("Sorry, I didn't catch that."))
                    continue

                text = self._apply_alias(stt_res.text).strip()
                if not text:
                    continue

                # stop word exits conversation window early
                if text.strip().lower() in ("stop", "cancel"):
                    self.active_until = 0
                    self.speaker.speak(self.personality.wrap("Okay."))
                    continue

                ctx = self._ctx()

                # 1) Try local skills
                skill_res = self.router.match_skill(text, ctx)
                if skill_res is not None and skill_res.ok:
                    reply = skill_res.text
                    self.speaker.speak(self.personality.wrap(reply))
                    continue

                # 2) LLM fallback (only if enabled or conversation mode active)
                llm_res = self.llm.generate(user_text=text, system_prompt=self._system_prompt())
                if llm_res.ok and llm_res.text:
                    self.memory.add_event("voice", text, intent="llm:fallback", success=True, meta={})
                    self.speaker.speak(self.personality.wrap(llm_res.text))
                else:
                    self.memory.add_event("voice", text, intent="llm:fallback", success=False, meta={"error": llm_res.error or ""})
                    self.speaker.speak(self.personality.wrap("I can help with time, status, or volume."))

        finally:
            self.stream.stop()

        # unreachable
        # return VoiceLoopStatus(True, "OK")
