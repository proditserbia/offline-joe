"""Dependency availability checks for Offline Joe diagnostics."""
from __future__ import annotations

import importlib
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class DepCheck:
    name: str
    ok: bool
    detail: str


def check_python_package(pkg: str, import_name: str | None = None) -> DepCheck:
    """Try to import *import_name* (defaults to *pkg*) and report result."""
    mod = import_name or pkg
    try:
        importlib.import_module(mod)
        return DepCheck(pkg, True, "ok")
    except Exception as exc:
        return DepCheck(pkg, False, str(exc))


def check_binary(cmd: str) -> DepCheck:
    """Check whether *cmd* is on PATH."""
    path = shutil.which(cmd)
    if path:
        return DepCheck(cmd, True, path)
    return DepCheck(cmd, False, "not found on PATH")


# Bundles of checks for the MS4 demo.
PYTHON_DEPS: list[tuple[str, str | None]] = [
    ("vosk", None),
    ("webrtcvad", None),
    ("numpy", None),
    ("openwakeword", None),   # optional
    ("fastapi", None),
    ("psutil", None),
    ("yaml", "yaml"),
]

SYSTEM_BINARIES: list[str] = [
    "arecord",
    "aplay",
    "espeak-ng",
    "piper",      # optional
    "ffmpeg",     # optional, for camera
    "rpicam-hello",  # optional, for camera probe
]


def run_all() -> list[DepCheck]:
    """Return a list of :class:`DepCheck` for all MS4 dependencies."""
    results: list[DepCheck] = []
    for pkg, import_name in PYTHON_DEPS:
        results.append(check_python_package(pkg, import_name))
    for cmd in SYSTEM_BINARIES:
        results.append(check_binary(cmd))
    return results
