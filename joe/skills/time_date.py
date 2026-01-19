from __future__ import annotations
from datetime import datetime
from .base import SkillContext, SkillResult


def _ordinal(n: int) -> str:
    # 1st, 2nd, 3rd, 4th...
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _spoken_time_date(now: datetime) -> str:
    # Example: "It’s 10:08 PM on Friday, January 2nd, 2026."
    hour_12 = now.strftime("%I").lstrip("0") or "12"
    minute = now.strftime("%M")
    ampm = now.strftime("%p")
    weekday = now.strftime("%A")
    month = now.strftime("%B")
    day = _ordinal(now.day)
    year = now.year
    return f"It’s {hour_12}:{minute} {ampm} on {weekday}, {month} {day}, {year}."


class TimeDateSkill:
    name = "time_date"
    description = "Time/date queries."

    def run(self, text: str, ctx: SkillContext) -> SkillResult:
        now = datetime.now()
        return SkillResult(True, _spoken_time_date(now))
