from __future__ import annotations
import re
from .base import SkillContext, SkillResult

SLEEP = re.compile(r"\b(go to sleep|sleep mode)\b", re.I)
WAKE = re.compile(r"\b(wake up|wake mode)\b", re.I)

class ModeSkill:
    name = "mode"
    description = "Wake/sleep mode."

    def run(self, text: str, ctx: SkillContext) -> SkillResult:
        raw = text.strip()
        if SLEEP.search(raw):
            ctx.state.set_awake(False)
            return SkillResult(True, "All right. Going to sleep mode.")
        if WAKE.search(raw):
            ctx.state.set_awake(True)
            return SkillResult(True, "I am awaked.")
        return SkillResult(False, "Not mode.")
