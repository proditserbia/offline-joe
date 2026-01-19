from __future__ import annotations
from .base import SkillContext, SkillResult

class MemorySkill:
    name = "memory"
    description = "Memory save/recall/clear/list."

    def run(self, text: str, ctx: SkillContext) -> SkillResult:
        t = text.strip().lower()
        if "clear memory" in t:
            n1 = ctx.memory.clear_events()
            n2 = ctx.memory.clear_facts()
            return SkillResult(True, f"I cleaned up memory. Events: {n1}, Facts: {n2}.")
        if "list memory" in t:
            items = ctx.memory.list_events(limit=10)
            lines = [f"{e['id']}: {e['text']}" for e in items]
            return SkillResult(True, "Last events:\n" + "\n".join(lines), data={"events": items})
        return SkillResult(False, "I cant understand memory command.")
