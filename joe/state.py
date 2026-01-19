from __future__ import annotations
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

@dataclass
class JoeState:
    awake: bool = True
    last_user_text: str | None = None
    lock: RLock = field(default_factory=RLock, repr=False)

    def set_awake(self, value: bool) -> None:
        with self.lock:
            self.awake = value

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"awake": self.awake, "last_user_text": self.last_user_text}
