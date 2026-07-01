"""Shared Anthropic LLM instance."""
from __future__ import annotations

from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from kwabo.config import settings
from kwabo.config_store import effective_setting


@lru_cache(maxsize=8)
def _build_llm(model: str, temperature: float) -> ChatAnthropic:
    return ChatAnthropic(
        model=model,
        temperature=temperature,
        api_key=settings.anthropic_api_key,
        max_tokens=16000,
    )


def get_llm() -> ChatAnthropic:
    # Keyed op de effectieve model/temperature: een wijziging in de Configuratie
    # levert vanzelf een nieuwe (gecachete) instance op — geen cache_clear nodig,
    # en robuust bij meerdere workers.
    model = effective_setting("anthropic_model", settings.anthropic_model)
    temperature = float(effective_setting("llm_temperature", 0.0))
    return _build_llm(model, temperature)
