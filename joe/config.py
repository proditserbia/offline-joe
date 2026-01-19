from __future__ import annotations
from dataclasses import dataclass
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

def load_settings() -> Settings:
    base = Path(os.environ.get("JOE_DATA_DIR", str(Path.home() / ".offlinejoe")))
    base.mkdir(parents=True, exist_ok=True)
    db = Path(os.environ.get("JOE_DB_PATH", str(base / "memory.sqlite3")))

    hw_path = Path(os.environ.get("JOE_HARDWARE_YAML", str(Path.cwd() / "config" / "hardware.yaml")))
    if not hw_path.exists():
        # fallback to user's data_dir if they copied it there
        alt = base / "hardware.yaml"
        if alt.exists():
            hw_path = alt
    hardware = load_hardware_config(hw_path) if hw_path.exists() else None
    if hardware is None:
        raise FileNotFoundError(
            f"hardware.yaml not found. Set JOE_HARDWARE_YAML or place config/hardware.yaml. Tried: {hw_path}"
        )

    return Settings(data_dir=base, db_path=db, hardware_path=hw_path, hardware=hardware)
