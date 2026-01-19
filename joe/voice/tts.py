from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile


@dataclass
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

        # piper
        if self.piper_model_path and shutil.which("piper"):
            try:
                with tempfile.TemporaryDirectory() as td:
                    wav = Path(td) / "tts.wav"
                    cmd = [
                        "piper",
                        "--model",
                        self.piper_model_path,
                        "--output_file",
                        str(wav),
                    ]
                    subprocess.run(cmd, input=t.encode("utf-8"), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    # play
                    play = ["aplay", "-q", "-D", self.output_device, str(wav)]
                    subprocess.run(play, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    return TtsResult(True)
            except Exception as e:
                # fall through to espeak
                last_err = str(e)
        else:
            last_err = None

        # espeak fallback
        if shutil.which("espeak-ng"):
            try:
                cmd = ["espeak-ng", "-s", "165", "-v", "en-us", t]
                # Route to ALSA via aplay using wave? espeak can output to stdout (-w)
                with tempfile.TemporaryDirectory() as td:
                    wav = Path(td) / "espeak.wav"
                    gen = ["espeak-ng", "-s", "165", "-v", "en-us", "-w", str(wav), t]
                    subprocess.run(gen, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    subprocess.run(["aplay", "-q", "-D", self.output_device, str(wav)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return TtsResult(True)
            except Exception as e:
                return TtsResult(False, error=str(e))

        return TtsResult(False, error=last_err or "No TTS backend found (install piper or espeak-ng)")
