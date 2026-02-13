from __future__ import annotations
import re
from .base import SkillContext, SkillResult

NAME_PATTERNS = [
    re.compile(r"\bmy name is\s+(.+)$", re.I),
#    re.compile(r"\bzovem se\s+(.+)$", re.I),
#    re.compile(r"\bja sam\s+(.+)$", re.I),
]
ASK_NAME_PATTERNS = [
    re.compile(r"\bwhat('s| is)\s+my\s+name\b", re.I),
#    re.compile(r"\bkako se zovem\b", re.I),
]

class FactsSkill:
    name = "facts"
    description = "Save/recall simple facts (e.g., name)."

    def run(self, text: str, ctx: SkillContext) -> SkillResult:
        raw = text.strip()

        for p in NAME_PATTERNS:
            m = p.search(raw)
            if m:
                name = m.group(1).strip().strip(".!")
                name = " ".join(w.capitalize() for w in name.split())
                ctx.memory.set_fact("user", "name", name, source=ctx.source, confidence=1.0)
                return SkillResult(True, f"I remember: your name is {name}.", data={"name": name})

        for p in ASK_NAME_PATTERNS:
            if p.search(raw):
                name = ctx.memory.get_fact("user", "name")
                if name:
                    return SkillResult(True, f"Your name is {name}.", data={"name": name})
                return SkillResult(True, "I dont know your name yet. Say: 'my name is ...'.")

        return SkillResult(False, "Not facts.")
