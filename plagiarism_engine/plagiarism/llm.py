"""채팅 LLM 프로바이더 스위치 (Ollama ↔ OpenAI) — authoring_engine.llm과 동일 패턴.

env(호출 시점 조회): JCQ_LLM_PROVIDER(ollama|openai), JCQ_OPENAI_API_KEY/MODEL/BASE_URL.
"""
from __future__ import annotations

import os
from typing import Any


def current_provider() -> str:
    return os.getenv("JCQ_LLM_PROVIDER", "ollama").strip().lower()


def make_chat_model(model: str, *, temperature: float, num_ctx: int | None = None) -> Any:
    if current_provider() == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": os.getenv("JCQ_OPENAI_MODEL", "gpt-4o-mini"),
            "temperature": temperature,
        }
        key = os.getenv("JCQ_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if key:
            kwargs["api_key"] = key
        base = os.getenv("JCQ_OPENAI_BASE_URL", "").strip()
        if base:
            kwargs["base_url"] = base
        return ChatOpenAI(**kwargs)

    from langchain_ollama import ChatOllama

    from . import config

    kwargs = {
        "model": model,
        "temperature": temperature,
        "base_url": config.OLLAMA_BASE_URL,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
    }
    if num_ctx is not None:
        kwargs["num_ctx"] = num_ctx
    return ChatOllama(**kwargs)
