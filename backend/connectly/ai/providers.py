"""Language model providers for brief summaries. All optional; the platform works without any.

"gemini" uses the Google Gemini API on its free tier only, through connectly.ai.gemini (model
allow-list, local limits, usage accounting). "ollama" and "openai_compatible" are for free,
self-hosted servers. The deterministic engines never depend on any of these.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from connectly.core.config import Settings, get_settings


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


@dataclass
class OllamaProvider:
    base_url: str
    model: str
    timeout: float
    name: str = "ollama"

    def complete(self, system: str, user: str) -> str:
        try:
            r = httpx.post(
                f"{self.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "options": {"temperature": 0},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise ProviderError(f"Ollama request failed: {e}") from e


@dataclass
class OpenAICompatibleProvider:
    base_url: str
    model: str
    timeout: float
    api_key: str | None = None
    name: str = "openai_compatible"

    def complete(self, system: str, user: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = httpx.post(
                f"{self.base_url.rstrip('/')}/v1/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"model server request failed: {e}") from e


@dataclass
class GeminiProvider:
    model: str
    name: str = "gemini"

    def complete(self, system: str, user: str) -> str:
        from sqlalchemy.orm import Session

        from connectly.ai.gemini import GeminiClient, GeminiError
        from connectly.core.db import get_engine

        with Session(get_engine()) as session, GeminiClient(session) as client:
            try:
                return client.text_answer(user, system)
            except GeminiError as e:
                raise ProviderError(str(e)) from None


def get_provider(settings: Settings | None = None) -> Provider | None:
    s = settings or get_settings()
    kind = s.ai_provider.lower()
    if kind == "none":
        return None
    if kind == "ollama":
        return OllamaProvider(s.ai_base_url, s.ai_model, s.ai_timeout)
    if kind == "openai_compatible":
        return OpenAICompatibleProvider(s.ai_base_url, s.ai_model, s.ai_timeout, s.ai_api_key)
    if kind == "gemini":
        from connectly.ai.gemini import FREE_TEXT_MODELS

        if not s.gemini_api_key:
            raise ProviderError("ai_provider is gemini but CONNECTLY_GEMINI_API_KEY is not set")
        if s.gemini_text_model not in FREE_TEXT_MODELS:
            raise ProviderError(
                f"{s.gemini_text_model} is not on the free-tier list ({', '.join(sorted(FREE_TEXT_MODELS))})"
            )
        return GeminiProvider(s.gemini_text_model)
    raise ProviderError(
        f"unknown ai_provider {s.ai_provider!r} (none, gemini, ollama, openai_compatible)"
    )
