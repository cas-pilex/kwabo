"""Shared Anthropic LLM instance."""
from __future__ import annotations

from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from kwabo.config import settings


@lru_cache(maxsize=1)
def get_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.anthropic_model,
        temperature=0,
        api_key=settings.anthropic_api_key,
        max_tokens=16000,
    )
