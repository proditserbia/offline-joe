from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any

from .skills.registry import SkillRegistry
from .skills.base import SkillContext, SkillResult

@dataclass
class Route:
    name: str
    skill: str
    pattern: re.Pattern[str]
    requires_awake: bool = True

class Router:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self.routes: list[Route] = [
            Route("wake", "mode", re.compile(r"\b(wake up)\b", re.I), requires_awake=False),
            Route("sleep", "mode", re.compile(r"\b(go to sleep)\b", re.I), requires_awake=True),

            Route("volume", "voice", re.compile(r"\b(volume|set volume|mute|unmute)\b", re.I)),
            Route("time", "time_date", re.compile(r"\b(time|date)\b", re.I)),
            Route("status", "system_status", re.compile(r"\b(status|cpu|ram|disk|uptime|temperature|temp|ip)\b", re.I)),
            Route("facts_name_set", "facts", re.compile(r"\b(my name is)\b", re.I)),
            Route("facts_name_get", "facts", re.compile(r"\b(what'?s my name)\b", re.I)),
            Route("memory", "memory", re.compile(r"\b(clear memory|list memory)\b", re.I)),
        ]

    def match_skill(self, text: str, ctx: SkillContext) -> SkillResult | None:
        # wake/sleep gate
        if not ctx.state.awake:
            # allow only wake commands
            for r in self.routes:
                if not r.requires_awake and r.pattern.search(text):
                    return self._run(r.skill, text, ctx, route=r.name)
            return SkillResult(True, "Sleep mode. Say 'wake up'.")

        for r in self.routes:
            if r.pattern.search(text):
                return self._run(r.skill, text, ctx, route=r.name)

        return None

    def handle_text(self, text: str, ctx: SkillContext) -> SkillResult:
        """CLI/API-friendly routing.

        In MS4 voice mode we prefer `match_skill()` and then use LLM fallback.
        """
        res = self.match_skill(text, ctx)
        if res is not None:
            return res
        return SkillResult(False, "I am not sure what you want. Try: time, status, volume, 'my name is ...'.")

    def _run(self, skill_name: str, text: str, ctx: SkillContext, route: str) -> SkillResult:
        skill = self.registry.get(skill_name)
        res = skill.run(text, ctx)
        # log event
        ctx.memory.add_event(ctx.source, text, intent=f"{route}:{skill_name}", success=res.ok, meta=res.data or {})
        return res
