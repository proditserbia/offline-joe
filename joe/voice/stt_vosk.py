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

    def ready(self) -> bool:
        return self._Model is not None

    def _ensure_model(self):
        if self._model is None:
            self._model = self._Model(self.model_path)

    def transcribe_pcm_s16le(self, pcm: bytes) -> SttResult:
        if not self.ready():
            return SttResult(False, "", error="vosk not available")
        try:
            self._ensure_model()
            if self.grammar:
                rec = self._KaldiRecognizer(self._model, self.sample_rate, json.dumps(self.grammar))
            else:
                rec = self._KaldiRecognizer(self._model, self.sample_rate)

            rec.AcceptWaveform(pcm)
            res = json.loads(rec.FinalResult() or "{}")
            text = (res.get("text") or "").strip()
            return SttResult(True, text)
        except Exception as e:
            return SttResult(False, "", error=str(e))
