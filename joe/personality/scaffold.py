from __future__ import annotations

from dataclasses import dataclass

from ..hardware import PersonalityConfig


@dataclass(frozen=True)
class Personality:
    cfg: PersonalityConfig

    def wrap(self, text: str) -> str:
        """Deterministic, rule-based style wrapper.

        This is intentionally simple for MS4: no learning, no randomness.
        """
        t = (text or "").strip()
        if not t:
            t = "Okay."

        # Directness: shorten common filler
        if self.cfg.directness >= 2:
            t = t.replace("I think ", "").replace("I believe ", "")

        # Warmth: add gentle opener/closer
        if self.cfg.warmth >= 2 and not t.lower().startswith(("hi", "hello")):
            t = "Sure — " + t

        # Humor: tiny, safe lightness (no jokes that can derail)
        if self.cfg.humor >= 2:
            if not t.endswith(":)") and not t.endswith("😄"):
                t = t + " 🙂"

        return t
