from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence

log = logging.getLogger(__name__)


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def has_cmd(cmd: str) -> bool:
    return which(cmd) is not None


@dataclass(frozen=True)
class CmdResult:
    returncode: int
    stdout: str
    stderr: str


def run(
    cmd: Sequence[str],
    *,
    timeout_s: int = 5,
    check: bool = False,
    text: bool = True,
) -> CmdResult:
    """Run a command safely and capture output.

    Returns a lightweight result object so callers don't depend on subprocess internals.
    """
    try:
        cp = subprocess.run(
            list(cmd),
            capture_output=True,
            text=text,
            timeout=timeout_s,
            check=check,
        )
        return CmdResult(cp.returncode, cp.stdout or "", cp.stderr or "")
    except FileNotFoundError:
        return CmdResult(127, "", f"Command not found: {cmd[0]}")
    except subprocess.TimeoutExpired as e:
        return CmdResult(124, e.stdout or "", f"Timeout after {timeout_s}s")
    except subprocess.CalledProcessError as e:
        return CmdResult(int(e.returncode or 1), e.stdout or "", e.stderr or str(e))
    except Exception as e:
        log.exception("Command failed: %s", cmd)
        return CmdResult(1, "", f"{type(e).__name__}: {e}")
