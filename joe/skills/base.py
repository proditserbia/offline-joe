from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol

@dataclass
class SkillContext:
    source: str              # voice|cli|api
    state: Any               # JoeState
    memory: Any              # MemoryStore

@dataclass
class SkillResult:
    ok: bool
    text: str
    data: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = None  # e.g. {"type":"set_volume","value":50}

class Skill(Protocol):
    name: str
    description: str
    def run(self, text: str, ctx: SkillContext) -> SkillResult: ...
