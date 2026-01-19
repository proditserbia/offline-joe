from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass
class WakewordResult:
    triggered: bool
    score: float = 0.0
    error: str | None = None


def rms_int16(pcm: bytes) -> float:
    # pcm is little-endian int16
    if len(pcm) < 2:
        return 0.0
    n = len(pcm) // 2
    # compute RMS without numpy for minimal deps
    acc = 0.0
    for i in range(0, n * 2, 2):
        v = int.from_bytes(pcm[i:i+2], "little", signed=True)
        acc += float(v) * float(v)
    return math.sqrt(acc / max(n, 1))


class WakewordDetector:
    """openWakeWord-based detector (falls back to disabled if deps missing)."""

    def __init__(self, model_path: str | None, threshold: float, min_activation_frames: int, min_rms: int):
        self.model_path = model_path
        self.threshold = threshold
        self.min_activation_frames = min_activation_frames
        self.min_rms = min_rms
        self._streak = 0
        self._model = None

        try:
            from openwakeword.model import Model  # type: ignore
            if model_path:
                self._model = Model(wakeword_models=[model_path])
            else:
                self._model = Model()
        except Exception:
            self._model = None

    def ready(self) -> bool:
        return self._model is not None

    def process(self, pcm: bytes, sample_rate: int) -> WakewordResult:
        if not self._model:
            return WakewordResult(False, error="openwakeword not available")

        # RMS gate
        if rms_int16(pcm) < self.min_rms:
            self._streak = 0
            return WakewordResult(False, score=0.0)

        try:
            # openwakeword expects 16-bit PCM at 16k
            if sample_rate != 16000:
                return WakewordResult(False, error="Wakeword requires 16kHz PCM")

            scores = self._model.predict(pcm)
            # scores is dict: {model_name: score}
            score = float(max(scores.values())) if scores else 0.0

            if score >= self.threshold:
                self._streak += 1
            else:
                self._streak = 0

            if self._streak >= self.min_activation_frames:
                self._streak = 0
                return WakewordResult(True, score=score)

            return WakewordResult(False, score=score)
        except Exception as e:
            self._streak = 0
            return WakewordResult(False, error=str(e))
