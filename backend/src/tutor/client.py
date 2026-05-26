import os

from openai import AsyncOpenAI

from ..schemas import Problem
from .prompts import TUTOR_SYSTEM, render_user_message


async def tutor(
    *,
    problem: Problem,
    code: str,
    verdict: str | None,
    votes: list[dict] | None,
    test_results: list[dict],
    api_key: str,
) -> tuple[str, str]:
    """제출에 대한 튜터링 메시지를 생성한다. (message, model_name) 튜플 반환.

    api_key는 사용자가 등록한 교내 GPT 게이트웨이 키(Vault에서 복호화해 넘어옴).
    base_url/model은 서버 설정(OPENAI_BASE_URL / OPENAI_MODEL)에서 온다 —
    게이트웨이가 OpenAI 호환이라 키만 사용자별로 갈아끼우면 된다.
    사용자마다 키가 다르므로 클라이언트를 전역 캐시하지 않고 호출마다 새로 만든다.
    """
    model = os.getenv("OPENAI_MODEL", "gpt-5.1")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    user_msg = render_user_message(
        problem=problem,
        code=code,
        verdict=verdict,
        votes=votes,
        test_results=test_results,
    )
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TUTOR_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
        )
    finally:
        await client.close()
    msg = (resp.choices[0].message.content or "").strip()
    return msg, model
