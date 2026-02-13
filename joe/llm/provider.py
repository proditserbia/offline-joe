from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from ..hardware import LlmConfig


@dataclass(frozen=True)
class LlmReply:
    ok: bool
    text: str
    raw: dict[str, Any] | None = None
    error: str | None = None


class OpenAICompatibleLLM:
    """Tiny OpenAI-compatible Chat Completions client (MS4 scope)."""

    def __init__(self, cfg: LlmConfig):
        self.cfg = cfg
        self._session = requests.Session()

    def generate(self, *, user_text: str, system_prompt: str) -> LlmReply:
        if not self.cfg.enabled:
            return LlmReply(False, "", error="LLM disabled")

        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"

        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.4,
            "max_tokens": 200,
        }

        try:
            r = self._session.post(url, json=payload, headers=headers, timeout=(3.0, float(self.cfg.timeout_s)))
            r.raise_for_status()
            j = r.json()
            text = (((j.get("choices") or [{}])[0]).get("message", {}) or {}).get("content", "") or ""
            return LlmReply(True, text.strip(), raw=j)
        except requests.HTTPError as e:
            return LlmReply(False, "", error=f"HTTP {getattr(e.response,'status_code', '?')}: {getattr(e.response,'text','')[:200]}")
        except Exception as e:
            return LlmReply(False, "", error=f"{type(e).__name__}: {e}")
