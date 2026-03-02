from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
from .base import Skill
from . import TimeDateSkill, SystemStatusSkill, MemorySkill, FactsSkill, VoiceSkill, ModeSkill

@dataclass
class SkillRegistry:
    skills: Dict[str, Skill]

    @staticmethod
    def build_default(ssd_mount: str = "/mnt/ssd") -> "SkillRegistry":
        skills: Dict[str, Skill] = {}
        for s in [
            TimeDateSkill(),
            SystemStatusSkill(ssd_mount=ssd_mount),
            MemorySkill(),
            FactsSkill(),
            VoiceSkill(),
            ModeSkill(),
        ]:
            skills[s.name] = s
        return SkillRegistry(skills)

    def list(self) -> list[dict]:
        return [{"name": s.name, "description": s.description} for s in self.skills.values()]

    def get(self, name: str) -> Skill:
        if name not in self.skills:
            raise KeyError(f"Unknown skill: {name}")
        return self.skills[name]
