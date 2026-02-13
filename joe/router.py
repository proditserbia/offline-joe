from __future__ import annotations

from dataclasses import dataclass
import re

from .skills.base import SkillContext, SkillResult
from .skills.registry import SkillRegistry


@dataclass(frozen=True)
class Route:
    name: str
    skill: str
    pattern: re.Pattern[str]
    requires_awake: bool = True
    priority: int = 100  # lower runs first


class Router:
    """Rule-based router for deterministic local skills."""

    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self.routes: list[Route] = sorted(
            [
                Route("wake", "mode", re.compile(r"\b(wake up)\b", re.I), requires_awake=False, priority=0),
                Route("sleep", "mode", re.compile(r"\b(go to sleep)\b", re.I), requires_awake=True, priority=0),
                Route("volume", "voice", re.compile(r"\b(volume|set volume|mute|unmute)\b", re.I), priority=10),
                Route("time", "time_date", re.compile(r"\b(time|date)\b", re.I), priority=20),
                Route("status", "system_status", re.compile(r"\b(status|cpu|ram|disk|uptime|temperature|temp|ip)\b", re.I), priority=30),
                Route("facts_name_set", "facts", re.compile(r"\b(my name is)\b", re.I), priority=40),
                Route("facts_name_get", "facts", re.compile(r"\b(what'?s my name)\b", re.I), priority=40),
                Route("memory", "memory", re.compile(r"\b(clear memory|list memory)\b", re.I), priority=50),
            ],
            key=lambda r: r.priority,
        )

    def match_skill(self, text: str, ctx: SkillContext) -> SkillResult | None:
        t = (text or "").strip()
        if not t:
            return SkillResult(True, "Say something.")

        # record last text for status/debug
        if hasattr(ctx.state, "set_last_user_text"):
            ctx.state.set_last_user_text(t)

        # wake/sleep gate
        if not ctx.state.awake:
            for r in self.routes:
                if not r.requires_awake and r.pattern.search(t):
                    return self._run(r.skill, t, ctx, route=r.name)
            return SkillResult(True, "Sleep mode. Say 'wake up'.")

        for r in self.routes:
            if r.pattern.search(t):
                return self._run(r.skill, t, ctx, route=r.name)

        return None

    def handle_text(self, text: str, ctx: SkillContext) -> SkillResult:
        """CLI/API-friendly routing.

        In MS4 voice mode we prefer ``match_skill()`` and then use LLM fallback.
        """
        res = self.match_skill(text, ctx)
        if res is not None:
            return res
        return SkillResult(
            False,
            "I am not sure what you want. Try: time, status, volume, 'my name is ...'.",
        )

    def _run(self, skill_name: str, text: str, ctx: SkillContext, route: str) -> SkillResult:
        skill = self.registry.get(skill_name)
        res = skill.run(text, ctx)
        # log event
        ctx.memory.add_event(
            ctx.source,
            text,
            intent=f"{route}:{skill_name}",
            success=res.ok,
            meta=res.data or {},
        )
        return res
