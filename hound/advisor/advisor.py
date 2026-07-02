# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""LLMAdvisor — generates natural-language explanations for fired alerts."""

from __future__ import annotations

import os

from loguru import logger

from ..accumulate.state import AnalyzerState
from ..alerts.alert import Alert
from ..alerts.severity import Severity
from ..config.schema import LLMAdvisorConfig
from .prompt import build_prompt


class LLMAdvisor:
    """Calls an LLM API to explain a fired alert in plain English.

    Only active when ``config.enabled`` is True.  Supports Kimi (moonshot),
    OpenAI-compatible, and Anthropic providers.
    """

    def __init__(self, config: LLMAdvisorConfig) -> None:
        self._cfg = config

    def should_advise(self, alert: Alert) -> bool:
        if not self._cfg.enabled:
            return False
        return alert.severity.value in self._cfg.trigger_on

    def advise(self, alert: Alert, state: AnalyzerState) -> str | None:
        """Return LLM explanation string, or None on failure."""
        if not self.should_advise(alert):
            return None

        prompt = build_prompt(alert, state)
        try:
            return self._call_llm(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("hound: LLMAdvisor call failed: {}", exc)
            return None

    def _call_llm(self, prompt: str) -> str:
        provider = self._cfg.provider.lower()
        api_key = os.environ.get(self._cfg.api_key_env, "")

        # Split system / user from prompt string
        system_text = ""
        user_text = prompt
        if prompt.startswith("SYSTEM: "):
            parts = prompt.split("\n\nUSER:\n", 1)
            system_text = parts[0].replace("SYSTEM: ", "", 1)
            user_text = parts[1] if len(parts) > 1 else prompt

        if provider in ("kimi", "moonshot", "openai"):
            return self._call_openai_compat(system_text, user_text, api_key)
        elif provider == "anthropic":
            return self._call_anthropic(system_text, user_text, api_key)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _call_openai_compat(self, system: str, user: str, api_key: str) -> str:
        import urllib.request, json

        base_url = "https://api.moonshot.cn/v1" if self._cfg.provider in ("kimi", "moonshot") else "https://api.openai.com/v1"
        payload = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 600,
            "temperature": 0.3,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"].strip()

    def _call_anthropic(self, system: str, user: str, api_key: str) -> str:
        import urllib.request, json

        payload = {
            "model": self._cfg.model,
            "max_tokens": 600,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["content"][0]["text"].strip()
