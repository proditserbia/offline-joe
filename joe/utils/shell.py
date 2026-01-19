from __future__ import annotations
import shutil
import subprocess

def which(cmd: str) -> str | None:
    return shutil.which(cmd)

def run(cmd: list[str], timeout: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def has_cmd(cmd: str) -> bool:
    return which(cmd) is not None
