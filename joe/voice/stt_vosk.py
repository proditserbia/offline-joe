from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import json


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
            self._model = self._Model(self.model_path)

    def _ensure_recognizer(self):
        """Create/reuse a KaldiRecognizer.

        Important: Creating a recognizer with constrained grammar triggers Vosk's
        internal grammar FST build (UpdateGrammarFst), which is expensive and noisy.
        We therefore create the recognizer once and reuse it, only recreating if the
        grammar changes.
        """
        if self._KaldiRecognizer is None:
            return

        grammar_json = json.dumps(self.grammar) if self.grammar else None
        if self._rec is not None and grammar_json == self._grammar_json:
            return

        # (Re)create recognizer
        if grammar_json is not None:
            self._rec = self._KaldiRecognizer(self._model, self.sample_rate, grammar_json)
        else:
            self._rec = self._KaldiRecognizer(self._model, self.sample_rate)
        self._grammar_json = grammar_json

    def transcribe_pcm_s16le(self, pcm: bytes) -> SttResult:
        if not self.ready():
            return SttResult(False, "", error="vosk not available")
        try:
            self._ensure_model()
            self._ensure_recognizer()

            # Reset recognizer state for a new utterance.
            # This avoids rebuilding grammar each call while still returning clean results.
            if hasattr(self._rec, "Reset"):
                self._rec.Reset()

            self._rec.AcceptWaveform(pcm)
            res = json.loads(self._rec.FinalResult() or "{}")
            text = (res.get("text") or "").strip()
            return SttResult(True, text)
        except Exception as e:
            return SttResult(False, "", error=str(e))
