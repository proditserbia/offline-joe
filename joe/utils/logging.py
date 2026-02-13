from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable


def configure_logging(
    *,
    level: str | int | None = None,
    log_dir: Path | None = None,
    log_file_name: str = "offlinejoe.log",
    max_bytes: int = 2_000_000,
    backup_count: int = 3,
    noisy_loggers: Iterable[str] = ("uvicorn.access",),
) -> None:
    """Configure a sane default logging setup.

    - Console logs always enabled
    - Optional rotating file logs under ``log_dir``
    - Respects env vars:
        - JOE_LOG_LEVEL (e.g. INFO, DEBUG)
        - JOE_LOG_DIR (e.g. ~/.offlinejoe/logs)
    """
    env_level = os.getenv("JOE_LOG_LEVEL")
    if level is None and env_level:
        level = env_level

    if isinstance(level, str):
        level = level.upper().strip()
    level_value = logging.INFO if level in (None, "") else logging.getLevelName(level)
    if isinstance(level_value, str):
        # Unknown string; fall back.
        level_value = logging.INFO

    root = logging.getLogger()
    root.setLevel(level_value)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Avoid double handlers on reload
    if getattr(root, "_offlinejoe_configured", False):
        return

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    env_dir = os.getenv("JOE_LOG_DIR")
    if log_dir is None and env_dir:
        log_dir = Path(env_dir).expanduser()

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            filename=str(log_dir / log_file_name),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)

    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    root._offlinejoe_configured = True  # type: ignore[attr-defined]
