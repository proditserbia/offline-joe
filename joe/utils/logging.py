from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Format strings
# ---------------------------------------------------------------------------
#: Full format used for file handlers and when DEBUG level is active.
_FMT_FULL = (
    "%(asctime)s | %(levelname)-8s | %(name)s | "
    "%(threadName)s | %(filename)s:%(lineno)d | %(message)s"
)
#: Compact format for console output (INFO and above).
_FMT_CONSOLE = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Module-level logger (used for startup/shutdown audit messages)
# ---------------------------------------------------------------------------
_log = logging.getLogger(__name__)


def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger for *name*.

    Convenience wrapper so callers don't need to import ``logging`` directly.
    """
    return logging.getLogger(name)


def configure_logging(
    *,
    level: str | int | None = None,
    log_dir: Path | None = None,
    log_file_name: str = "offlinejoe.log",
    max_bytes: int = 10_000_000,
    backup_count: int = 5,
    noisy_loggers: Iterable[str] = (
        "uvicorn.access",
        "httpx",
        "httpcore",
        "vosk",
    ),
) -> None:
    """Configure enterprise-grade logging for Offline Joe.

    Features
    --------
    - Console handler always attached (compact format).
    - Rotating file handler when *log_dir* is set (full format with thread
      name, source file, and line number).
    - Level resolved from: *level* argument → ``JOE_LOG_LEVEL`` env var →
      ``INFO``.
    - ``JOE_LOG_DIR`` env var overrides *log_dir* when the argument is
      ``None``.
    - Idempotent: calling multiple times in the same process is safe.
    - Noisy third-party loggers clamped to ``WARNING``.

    Environment variables
    ---------------------
    ``JOE_LOG_LEVEL``
        Override the log level (e.g. ``DEBUG``, ``INFO``, ``WARNING``).
    ``JOE_LOG_DIR``
        Directory for the rotating log file.  The directory is created if
        it does not exist.
    """
    # --- Resolve effective log level ----------------------------------------
    env_level = os.getenv("JOE_LOG_LEVEL")
    if level is None and env_level:
        level = env_level

    if isinstance(level, str):
        level = level.upper().strip()
    level_value: int = (
        logging.INFO if level in (None, "")
        else logging.getLevelName(level)  # type: ignore[arg-type]
    )
    if not isinstance(level_value, int):
        # getLevelName returned a string for an unknown level name.
        level_value = logging.INFO

    # --- Idempotency guard --------------------------------------------------
    root = logging.getLogger()
    if getattr(root, "_offlinejoe_configured", False):
        # Already configured; just update the effective level if caller raised it.
        if level_value < root.level:
            root.setLevel(level_value)
        return
    root.setLevel(level_value)

    # --- Console handler (compact) ------------------------------------------
    console_fmt = logging.Formatter(fmt=_FMT_CONSOLE, datefmt=_DATEFMT)
    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(console_fmt)
    # Console shows DEBUG when the effective level is DEBUG; otherwise INFO+.
    ch.setLevel(logging.DEBUG if level_value <= logging.DEBUG else logging.INFO)
    root.addHandler(ch)

    # --- File handler (full, rotating) --------------------------------------
    env_dir = os.getenv("JOE_LOG_DIR")
    if log_dir is None and env_dir:
        log_dir = Path(env_dir).expanduser()

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_fmt = logging.Formatter(fmt=_FMT_FULL, datefmt=_DATEFMT)
        fh = RotatingFileHandler(
            filename=str(log_dir / log_file_name),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        fh.setFormatter(file_fmt)
        fh.setLevel(logging.DEBUG)  # file captures everything
        root.addHandler(fh)

    # --- Suppress noisy third-party loggers ---------------------------------
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Mark configured and emit audit record.
    root._offlinejoe_configured = True  # type: ignore[attr-defined]
    _log.info(
        "Logging initialized: level=%s file=%s python=%s",
        logging.getLevelName(level_value),
        str(log_dir / log_file_name) if log_dir else "none",
        sys.version.split()[0],
    )
