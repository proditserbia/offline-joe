from __future__ import annotations

from dataclasses import dataclass
import json
import logging

log = logging.getLogger(__name__)


@dataclass
class SttResult:
    ok: bool
    text: str
    error: str | None = None


class VoskSTT:
    def __init__(self, model_path: str, sample_rate: int = 16000, grammar: list[str] | None = None):
        try:
            from vosk import Model, KaldiRecognizer  # type: ignore
            self._Model = Model
            self._KaldiRecognizer = KaldiRecognizer
        except Exception:
            self._Model = None
            self._KaldiRecognizer = None
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.grammar = grammar or []
        self._model = None
        self._rec = None
        self._grammar_json: str | None = None

    def ready(self) -> bool:
        return self._Model is not None

    def _ensure_model(self):
        if self._model is None:
            log.debug("STT model init path=%s sample_rate=%d", self.model_path, self.sample_rate)
            self._model = self._Model(self.model_path)

    def _ensure_recognizer(self):
        """
        Create/reuse a KaldiRecognizer.

        Creating recognizer with constrained grammar triggers grammar FST build,
        so we reuse recognizer unless grammar changed.
        """
        if self._KaldiRecognizer is None:
            return

        grammar_json = json.dumps(self.grammar) if self.grammar else None
        if self._rec is not None and grammar_json == self._grammar_json:
            return

        if grammar_json is not None:
            self._rec = self._KaldiRecognizer(self._model, self.sample_rate, grammar_json)
            log.debug("STT recognizer (re)created with grammar size=%d", len(self.grammar))
        else:
            self._rec = self._KaldiRecognizer(self._model, self.sample_rate)
            log.debug("STT recognizer (re)created without grammar")

        self._grammar_json = grammar_json

    def transcribe_pcm_s16le(self, pcm: bytes) -> SttResult:
        if not self.ready():
            return SttResult(False, "", error="vosk not available")
        try:
            self._ensure_model()
            self._ensure_recognizer()

            if hasattr(self._rec, "Reset"):
                self._rec.Reset()

            self._rec.AcceptWaveform(pcm)
            res = json.loads(self._rec.FinalResult() or "{}")
            text = (res.get("text") or "").strip()

            if text:
                log.info("voice.stt.final text=%r chars=%d", text, len(text))
            else:
                log.debug("voice.stt.final empty=true")

            return SttResult(True, text)
        except Exception as e:
            log.exception("voice.stt.error: %s", e)
            return SttResult(False, "", error=str(e))
