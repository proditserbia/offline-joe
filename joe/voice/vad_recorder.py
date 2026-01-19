from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VadRecorderConfig:
    aggressiveness: int = 2
    silence_ms: int = 800
    max_record_ms: int = 8000
    sample_rate: int = 16000


class VadRecorder:
    """Collects speech audio from a PCM stream using webrtcvad.

    Records once speech is detected, then stops after `silence_ms` of silence
    or when reaching `max_record_ms`.
    """

    def __init__(self, cfg: VadRecorderConfig):
        self.cfg = cfg
        try:
            import webrtcvad  # type: ignore
            self._vad = webrtcvad.Vad(cfg.aggressiveness)
        except Exception:
            self._vad = None

        # webrtcvad supports 10,20,30ms frames
        self.frame_ms = 20
        self.frame_bytes = int(self.cfg.sample_rate * (self.frame_ms / 1000.0) * 2)  # int16

    def ready(self) -> bool:
        return self._vad is not None

    def record_one_utterance(self, stream, pre_roll_ms: int = 200) -> bytes:
        if not self._vad:
            raise RuntimeError("webrtcvad not available")

        pre_roll_frames = max(0, int(pre_roll_ms / self.frame_ms))
        silence_frames = max(1, int(self.cfg.silence_ms / self.frame_ms))
        max_frames = max(1, int(self.cfg.max_record_ms / self.frame_ms))

        ring: list[bytes] = []
        voiced: list[bytes] = []

        in_speech = False
        silent_run = 0

        for _ in range(max_frames):
            frame = stream.read(self.frame_bytes)
            if not frame or len(frame) < self.frame_bytes:
                break

            is_speech = self._vad.is_speech(frame, self.cfg.sample_rate)

            if not in_speech:
                ring.append(frame)
                if len(ring) > pre_roll_frames:
                    ring.pop(0)
                if is_speech:
                    in_speech = True
                    voiced.extend(ring)
                    ring.clear()
            else:
                voiced.append(frame)
                if is_speech:
                    silent_run = 0
                else:
                    silent_run += 1
                    if silent_run >= silence_frames:
                        break

        return b"".join(voiced)
