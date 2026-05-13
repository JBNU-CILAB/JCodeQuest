"""채점 엔진(judge_engine) HTTP 클라이언트.

채점 자체는 judge_engine 내부의 큐+워커가 비동기로 수행한다. backend는 큐잉 요청만
보내고 즉시 반환 — 결과는 backend의 `/internal/grade-events` 로 webhook 회신.
"""
from __future__ import annotations

import logging
import os

import httpx

from ..schemas import GradeSubmitRequest, Problem

log = logging.getLogger(__name__)

# 큐잉 요청 자체는 즉시 202가 떨어지므로 짧게 잡음. 채점 처리시간과는 무관.
_SUBMIT_TIMEOUT_S = 10.0


def _judge_url() -> str:
    return os.getenv("JCQ_JUDGE_URL", "http://127.0.0.1:8002").rstrip("/")


async def submit_to_engine(submission_id: int, problem: Problem, code: str) -> None:
    """judge_engine 큐에 채점 작업을 적재하고 즉시 반환.

    raises:
        httpx.HTTPError: judge_engine이 응답하지 않거나 4xx/5xx를 반환할 때.
                         호출자가 잡아서 submission status='failed'로 마킹할 책임.
    """
    payload = GradeSubmitRequest(submission_id=submission_id, problem=problem, code=code)
    async with httpx.AsyncClient(timeout=httpx.Timeout(_SUBMIT_TIMEOUT_S)) as cli:
        r = await cli.post(f"{_judge_url()}/api/grade", json=payload.model_dump())
        r.raise_for_status()
