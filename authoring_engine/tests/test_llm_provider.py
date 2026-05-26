"""llm.make_chat_model — 로컬 Ollama ↔ OpenAI 프로바이더 스위치.

생성만 검증(네트워크/실키 불필요): provider env에 따라 올바른 클래스/모델을 만드는지.
"""
from __future__ import annotations

from authoring.llm import current_provider, make_chat_model


def test_default_provider_is_ollama(monkeypatch):
    monkeypatch.delenv("JCQ_LLM_PROVIDER", raising=False)
    assert current_provider() == "ollama"
    from langchain_ollama import ChatOllama

    m = make_chat_model("qwen2.5-coder:14b", temperature=0, json_mode=True, num_ctx=8192)
    assert isinstance(m, ChatOllama)
    assert m.model == "qwen2.5-coder:14b"  # ollama 모델명 그대로 전달


def test_openai_provider_overrides_model(monkeypatch):
    monkeypatch.setenv("JCQ_LLM_PROVIDER", "openai")
    monkeypatch.setenv("JCQ_OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("JCQ_OPENAI_MODEL", "gpt-4o-mini")
    from langchain_openai import ChatOpenAI

    # ollama 모델명을 넘겨도 openai 모드에선 JCQ_OPENAI_MODEL로 대체돼야 한다
    m = make_chat_model("qwen2.5-coder:14b", temperature=0, json_mode=True, num_ctx=8192)
    assert isinstance(m, ChatOpenAI)
    assert getattr(m, "model_name", getattr(m, "model", None)) == "gpt-4o-mini"


def test_openai_falls_back_to_standard_key_env(monkeypatch):
    monkeypatch.setenv("JCQ_LLM_PROVIDER", "openai")
    monkeypatch.delenv("JCQ_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-standard-dummy")
    from langchain_openai import ChatOpenAI

    m = make_chat_model("ignored", temperature=0.2)
    assert isinstance(m, ChatOpenAI)


def test_provider_value_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("JCQ_LLM_PROVIDER", "OpenAI")
    assert current_provider() == "openai"
