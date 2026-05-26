"""채팅 LLM 프로바이더 스위치 — 로컬 Ollama ↔ OpenAI(호환 엔드포인트 포함).

출제 파이프라인의 모든 노드(generate/verify/judge/solve/attack/compare)는 여기
`make_chat_model`로 모델을 만든다. 기본은 Ollama(기존 동작)이고,
`JCQ_LLM_PROVIDER=openai`면 OpenAI로 빠르게 갈아끼워 생성 속도를 높일 수 있다.

env(호출 시점 조회 — 서버 재시작 없이 바뀌어도 반영):
  JCQ_LLM_PROVIDER     ollama(기본) | openai
  JCQ_OPENAI_API_KEY   OpenAI 키 (없으면 표준 OPENAI_API_KEY로 폴백)
  JCQ_OPENAI_MODEL     openai일 때 전 노드 공통 모델 (기본 gpt-4o-mini)
  JCQ_OPENAI_BASE_URL  OpenAI 호환 엔드포인트 (비우면 api.openai.com; gpt.jbnu.ai 등 가능)

주의: openai 모드에선 3-judge 앙상블이 모두 같은 모델(JCQ_OPENAI_MODEL)을 쓴다 —
다양성은 줄지만 중앙값/2-of-3 판정은 그대로 동작한다(빠른 검증용). 임베딩(novelty·RAG)은
별도로 Ollama를 그대로 쓴다(저장된 bge-m3 벡터와 차원을 맞춰야 하므로). Ollama가 없으면
novelty·RAG는 fail-open으로 건너뛴다.
"""
from __future__ import annotations

import os
from typing import Any


def current_provider() -> str:
    return os.getenv("JCQ_LLM_PROVIDER", "ollama").strip().lower()


def make_chat_model(
    model: str,
    *,
    temperature: float,
    json_mode: bool = False,
    num_ctx: int | None = None,
) -> Any:
    """노드가 쓰는 채팅 모델을 프로바이더에 맞게 생성한다.

    model/num_ctx는 Ollama용 인자다. openai 모드에선 model을 JCQ_OPENAI_MODEL로
    대체하고 num_ctx/keep_alive는 무시한다. json_mode면 각 프로바이더의 JSON 강제
    옵션(Ollama format="json" / OpenAI response_format)을 건다.
    """
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
        if json_mode:
            # response_format=json_object는 프롬프트에 'json' 언급이 있어야 함 — 모든
            # json_mode 프롬프트가 JSON 출력을 명시하므로 충족.
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatOpenAI(**kwargs)

    # 기본: 로컬 Ollama
    from langchain_ollama import ChatOllama

    from .config import OLLAMA_BASE_URL, OLLAMA_KEEP_ALIVE

    kwargs = {
        "model": model,
        "temperature": temperature,
        "base_url": OLLAMA_BASE_URL,
        "keep_alive": OLLAMA_KEEP_ALIVE,
    }
    if json_mode:
        kwargs["format"] = "json"
    if num_ctx is not None:
        kwargs["num_ctx"] = num_ctx
    return ChatOllama(**kwargs)
