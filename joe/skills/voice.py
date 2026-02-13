from __future__ import annotations
import re
from .base import SkillContext, SkillResult
from ..audio.volume import set_volume_percent, get_volume_percent, mute

SET_VOL = re.compile(r"(?:set\s+volume\s+to|volume)\s+(\d{1,3})%?", re.I)
MUTE = re.compile(r"\b(mute)\b", re.I)
UNMUTE = re.compile(r"\b(unmute)\b", re.I)
GET = re.compile(r"\b(what'?s the volume|volume status)\b", re.I)

class VoiceSkill:
    name = "voice"
    description = "Volume / mute controls (auto-detect pactl/amixer)."

    def run(self, text: str, ctx: SkillContext) -> SkillResult:
        raw = text.strip()

        m = SET_VOL.search(raw)
        if m:
            v = int(m.group(1))
            ok = set_volume_percent(v)
            return SkillResult(ok, "I seted at {}%.".format(max(0, min(100, v))) if ok else "I can not set up volume.")

        if MUTE.search(raw):
            ok = mute(True)
            return SkillResult(ok, "Mute turned on." if ok else "I cannot mute volume.")

        if UNMUTE.search(raw):
            ok = mute(False)
            return SkillResult(ok, "Mute turned off." if ok else "I can not unmute volume.")

        if GET.search(raw):
            v = get_volume_percent()
            if v is None:
                return SkillResult(False, "I can not decrease volume.")
            return SkillResult(True, f"Volume is {v}%.", data={"volume": v})

        return SkillResult(False, "Not voice.")
