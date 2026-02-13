from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlsaStreamConfig:
    device: str
    rate: int = 16000
    channels: int = 1


class AlsaPCMStream:
    """Read raw 16-bit little-endian PCM from ``arecord`` stdout."""

    def __init__(self, cfg: AlsaStreamConfig):
        self.cfg = cfg
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if self.proc:
            return
        if not shutil.which("arecord"):
            raise RuntimeError("arecord not found. Install ALSA utils: sudo apt install alsa-utils")

        cmd = [
            "arecord",
            "-q",
            "-f",
            "S16_LE",
            "-r",
            str(self.cfg.rate),
            "-c",
            str(self.cfg.channels),
            "-D",
            self.cfg.device,
            "-t",
            "raw",
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        if not self.proc.stdout:
            raise RuntimeError("arecord did not provide stdout")

    def read(self, n_bytes: int) -> bytes:
        if not self.proc or not self.proc.stdout:
            raise RuntimeError("stream not started")
        data = self.proc.stdout.read(int(n_bytes))
        if data is None:
            return b""
        return data

    def stop(self) -> None:
        if not self.proc:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
