from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile


@dataclass(frozen=True)
class TtsResult:
    ok: bool
    error: str | None = None


class Speaker:
    """TTS abstraction.

    Preferred: Piper CLI (offline, good quality).
    Fallback: espeak-ng (available on most Pi installs).
    """

    def __init__(self, output_device: str, piper_model_path: str | None = None):
        self.output_device = output_device
        self.piper_model_path = piper_model_path

    def speak(self, text: str) -> TtsResult:
        t = (text or "").strip()
        if not t:
            return TtsResult(True)

        last_err: str | None = None

        # Piper
        if self.piper_model_path and shutil.which("piper"):
            try:
                with tempfile.TemporaryDirectory() as td:
                    wav = Path(td) / "tts.wav"
                    subprocess.run(
                        ["piper", "--model", self.piper_model_path, "--output_file", str(wav)],
                        input=t.encode("utf-8"),
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    subprocess.run(
                        ["aplay", "-q", "-D", self.output_device, str(wav)],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                return TtsResult(True)
            except Exception as e:
                last_err = f"Piper failed: {type(e).__name__}: {e}"

        # espeak fallback
        if shutil.which("espeak-ng"):
            try:
                with tempfile.TemporaryDirectory() as td:
                    wav = Path(td) / "espeak.wav"
                    subprocess.run(
                        ["espeak-ng", "-s", "165", "-v", "en-us", "-w", str(wav), t],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    subprocess.run(
                        ["aplay", "-q", "-D", self.output_device, str(wav)],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                return TtsResult(True)
            except Exception as e:
                return TtsResult(False, error=f"espeak-ng failed: {type(e).__name__}: {e}")

        return TtsResult(False, error=last_err or "No TTS backend found (install piper or espeak-ng)")
