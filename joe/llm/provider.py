from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

from ..hardware import LlmConfig


@dataclass
class LlmReply:
    ok: bool
    text: str
    raw: dict | None = None
    error: str | None = None


class OpenAICompatibleLLM:
    """Very small OpenAI-compatible Chat Completions client.

    MS4 constraints:
    - single provider
    - no tools
    - no long-term memory
    - demo realism > depth
    """

    def __init__(self, cfg: LlmConfig):
        self.cfg = cfg

    def generate(self, user_text: str, system_prompt: str) -> LlmReply:
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
            r = requests.post(url, json=payload, headers=headers, timeout=self.cfg.timeout_s)
            r.raise_for_status()
            j = r.json()
            text = (
                (j.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return LlmReply(True, text, raw=j)
        except Exception as e:
            return LlmReply(False, "", error=str(e))
