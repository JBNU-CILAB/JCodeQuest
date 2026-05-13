"""내부 서비스 간 통신용 라우터. **공개 인터넷에 노출 금지** — reverse proxy 단에서
`/internal/*` 경로를 차단할 것. 인증은 `Authorization: Bearer <JCQ_INTERNAL_SECRET>`.

엔드포인트:
  POST /internal/grade-events   judge_engine이 채점 라이프사이클 이벤트를 push할 때 호출
"""
from __future__ import annotations

import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request

from ..events import SubmissionEventBroker
from ..judge.jobs import apply_grading_event
from ..schemas import GradeEvent

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _require_internal_auth(authorization: str | None) -> None:
    secret = os.getenv("JCQ_INTERNAL_SECRET", "")
    if not secret:
        # 시크릿 미설정 시 fail-closed — 잘못 켜 둔 채로 trust 흐름이 흐르지 않도록.
        raise HTTPException(503, "internal endpoint disabled (JCQ_INTERNAL_SECRET unset)")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(None, 1)[1].strip()
    if not hmac.compare_digest(token, secret):
        raise HTTPException(401, "invalid token")


@router.post(
    "/grade-events",
    summary="judge_engine → backend 채점 이벤트 webhook (내부 전용)",
)
async def grade_events(
    event: GradeEvent,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _require_internal_auth(authorization)
    broker: SubmissionEventBroker = request.app.state.events
    apply_grading_event(event, events=broker)
    return {"status": "ok"}
