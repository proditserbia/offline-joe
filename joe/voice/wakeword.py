from __future__ import annotations

import logging
import os
from array import array
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WakewordResult:
    triggered: bool
    score: float = 0.0
    error: str | None = None


def rms_int16(pcm: bytes) -> float:
    """Compute RMS of little-endian int16 PCM without numpy."""
    if len(pcm) < 2:
        return 0.0
    a = array("h")
    a.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not a:
        return 0.0
    acc = 0
    for v in a:
        acc += v * v
    return (acc / len(a)) ** 0.5


class WakewordDetector:
    """openWakeWord-based detector (falls back to disabled if deps missing)."""

    def __init__(self, model_path: str | None, threshold: float, min_activation_frames: int, min_rms: int):
        self.model_path = model_path
        self.threshold = float(threshold)
        self.min_activation_frames = int(min_activation_frames)
        self.min_rms = int(min_rms)
        self._streak = 0
        self._model = None

        # Prefer CPU-only inference in RPi/MS4 environments to avoid noisy provider warnings.
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("ORT_DISABLE_ARENA", "1")

        try:
            from openwakeword.model import Model  # type: ignore

            if model_path:
                # Keep constructor conservative for compatibility across openwakeword versions.
                self._model = Model(wakeword_models=[model_path])
            else:
                self._model = Model()

            log.debug(
                "WakewordDetector initialized model_path=%s threshold=%.3f min_frames=%d min_rms=%d",
                model_path,
                self.threshold,
                self.min_activation_frames,
                self.min_rms,
            )
        except Exception as exc:
            self._model = None
            log.warning("WakewordDetector unavailable: %s", exc)

    def ready(self) -> bool:
        return self._model is not None

    def process(self, pcm: bytes, *, sample_rate: int) -> WakewordResult:
        if not self._model:
            return WakewordResult(False, error="openwakeword not available")

        if rms_int16(pcm) < self.min_rms:
            self._streak = 0
            return WakewordResult(False, score=0.0)

        if sample_rate != 16000:
            self._streak = 0
            return WakewordResult(False, error="Wakeword requires 16kHz PCM")

        try:
            scores = self._model.predict(pcm)
            score = float(max(scores.values())) if scores else 0.0
            self._streak = self._streak + 1 if score >= self.threshold else 0

            if self._streak >= self.min_activation_frames:
                self._streak = 0
                return WakewordResult(True, score=score)

            return WakewordResult(False, score=score)
        except Exception as e:
            self._streak = 0
            return WakewordResult(False, error=f"{type(e).__name__}: {e}")
