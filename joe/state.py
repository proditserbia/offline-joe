from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass
class JoeState:
    """Minimal shared state between CLI/API/voice."""

    awake: bool = True
    last_user_text: str | None = None
    _lock: RLock = field(default_factory=RLock, repr=False)

    def set_awake(self, value: bool) -> None:
        with self._lock:
            self.awake = bool(value)

    def set_last_user_text(self, text: str | None) -> None:
        with self._lock:
            self.last_user_text = (text or "").strip() or None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"awake": self.awake, "last_user_text": self.last_user_text}
