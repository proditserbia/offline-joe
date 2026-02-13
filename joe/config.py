from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

from .hardware import HardwareConfig, load_hardware_config


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    hardware_path: Path
    hardware: HardwareConfig
    events_ttl_days: int = 30
    max_events: int = 50_000


def _resolve_path(p: str) -> Path:
    return Path(p).expanduser().resolve()


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Load application settings from env + hardware.yaml.

    Cached so importing modules won't re-read YAML repeatedly.
    """
    base = _resolve_path(os.environ.get("JOE_DATA_DIR", str(Path.home() / ".offlinejoe")))
    base.mkdir(parents=True, exist_ok=True)

    db = _resolve_path(os.environ.get("JOE_DB_PATH", str(base / "memory.sqlite3")))
    db.parent.mkdir(parents=True, exist_ok=True)

    hw_path = Path(os.environ.get("JOE_HARDWARE_YAML", str(Path.cwd() / "config" / "hardware.yaml"))).expanduser()
    if not hw_path.is_absolute():
        hw_path = (Path.cwd() / hw_path).resolve()

    if not hw_path.exists():
        # fallback to user's data_dir if they copied it there
        alt = base / "hardware.yaml"
        if alt.exists():
            hw_path = alt

    if not hw_path.exists():
        raise FileNotFoundError(
            "hardware.yaml not found. Set JOE_HARDWARE_YAML or place config/hardware.yaml. "
            f"Tried: {hw_path}"
        )

    hardware = load_hardware_config(hw_path)

    return Settings(data_dir=base, db_path=db, hardware_path=hw_path, hardware=hardware)
