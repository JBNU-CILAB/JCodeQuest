"""backend로 채점 이벤트를 webhook으로 보내는 콜백.

판정 결과는 단순 fire-and-forget이 아니라 ─ backend가 일시적으로 떠 있지 않을 가능성을
대비해 N회 지수 백오프 재시도한다. 다 실패하면 ERROR 로그를 남기고 포기 (영속 큐 없음 —
도입하려면 SQLite/Redis 어댑터로 승격 필요).
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx
from jcq_shared.schemas import GradeEvent

log = logging.getLogger(__name__)

_RETRY_BACKOFFS_S = (0.5, 2.0, 6.0)  # 총 ~8.5초, 3회 재시도


def _backend_url() -> str:
    return os.getenv("JCQ_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _secret() -> str:
    s = os.getenv("JCQ_INTERNAL_SECRET", "")
    if not s:
        # 비밀이 비어있으면 backend의 Bearer 검사도 통과 못함 — 즉시 알린다.
        log.error("JCQ_INTERNAL_SECRET 미설정 — webhook이 401로 거부될 것입니다")
    return s


async def send_event(event: GradeEvent) -> None:
    url = f"{_backend_url()}/internal/grade-events"
    headers = {"Authorization": f"Bearer {_secret()}"}
    body = event.model_dump()

    attempts = 1 + len(_RETRY_BACKOFFS_S)
    last_err: str = ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as cli:
        for i in range(attempts):
            try:
                r = await cli.post(url, json=body, headers=headers)
                if r.status_code < 400:
                    return
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                # 4xx면 재시도 무의미 (서명 불일치 등) — 즉시 종료
                if 400 <= r.status_code < 500:
                    log.error(
                        "webhook 거부 (재시도 안 함) submission=%d event=%s %s",
                        event.submission_id, event.event, last_err,
                    )
                    return
            except httpx.HTTPError as e:
                last_err = f"{type(e).__name__}: {e}"
            if i < len(_RETRY_BACKOFFS_S):
                await asyncio.sleep(_RETRY_BACKOFFS_S[i])

    log.error(
        "webhook 최종 실패 submission=%d event=%s — %s",
        event.submission_id, event.event, last_err,
    )
