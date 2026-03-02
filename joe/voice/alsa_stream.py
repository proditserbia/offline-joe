from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional


log = logging.getLogger(__name__)


@dataclass
class AlsaStreamConfig:
    device: str
    rate: int = 16000
    channels: int = 1


class AlsaPCMStream:
    """Read raw 16-bit little-endian PCM from `arecord` stdout."""

    def __init__(self, cfg: AlsaStreamConfig):
        self.cfg = cfg
        self.proc: subprocess.Popen[bytes] | None = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._bytes_read_total: int = 0
        self._t0: float = 0.0

    def start(self) -> None:
        if self.proc:
            return

        cmd = [
            "arecord",
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

        # We DO NOT use -q here during debugging; stderr is valuable.
        log.info("Starting arecord: %s", " ".join(cmd))
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._t0 = time.time()
        self._bytes_read_total = 0

        if not self.proc.stdout:
            raise RuntimeError("arecord did not provide stdout")
        if not self.proc.stderr:
            raise RuntimeError("arecord did not provide stderr")

        def _stderr_pump():
            assert self.proc and self.proc.stderr
            try:
                for line in iter(self.proc.stderr.readline, b""):
                    if not line:
                        break
                    s = line.decode("utf-8", errors="replace").rstrip()
                    if s:
                        log.warning("arecord stderr: %s", s)
            except Exception as e:
                log.exception("arecord stderr reader failed: %s", e)

        self._stderr_thread = threading.Thread(target=_stderr_pump, name="arecord-stderr", daemon=True)
        self._stderr_thread.start()

        log.info("arecord started pid=%s", self.proc.pid)

    def read(self, n_bytes: int) -> bytes:
        if not self.proc or not self.proc.stdout:
            raise RuntimeError("stream not started")

        data = self.proc.stdout.read(n_bytes)
        if not data:
            rc = self.proc.poll()
            log.error("arecord produced no data (len=0). poll()=%s", rc)
            return b""

        self._bytes_read_total += len(data)

        # lightweight throughput log every ~2s
        dt = max(time.time() - self._t0, 1e-6)
        if dt >= 2.0:
            bps = self._bytes_read_total / dt
            log.debug("arecord throughput: %.1f bytes/s (total=%d)", bps, self._bytes_read_total)
            # reset window
            self._t0 = time.time()
            self._bytes_read_total = 0

        return data

    def stop(self) -> None:
        if not self.proc:
            return
        log.info("Stopping arecord pid=%s", self.proc.pid)
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
