import os

from openai import AsyncOpenAI

from ..schemas import Problem
from .prompts import TUTOR_SYSTEM, render_user_message

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    # 모듈 로드 시 즉시 만들면 OPENAI_API_KEY 미설정 환경(import만 하는 테스트)에서 깨짐.
    # 처음 호출될 때 lazy 생성.
    # OPENAI_BASE_URL이 있으면 그 호환 엔드포인트를 사용 (vLLM, LM Studio, Ollama, Azure-proxy 등).
    global _client
    if _client is None:
        base_url = os.getenv("OPENAI_BASE_URL") or None
        _client = AsyncOpenAI(base_url=base_url)
    return _client


async def tutor(
    *,
    problem: Problem,
    code: str,
    verdict: str | None,
    votes: list[dict] | None,
    test_results: list[dict],
) -> tuple[str, str]:
    """제출에 대한 튜터링 메시지를 생성한다. (message, model_name) 튜플 반환."""
    model = os.getenv("OPENAI_MODEL", "gpt-5.1")
    user_msg = render_user_message(
        problem=problem,
        code=code,
        verdict=verdict,
        votes=votes,
        test_results=test_results,
    )
    resp = await _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TUTOR_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
    )
    msg = (resp.choices[0].message.content or "").strip()
    return msg, model
