"""관리자 대시보드 그래프용 통계 라우터 — backend /internal/stats 위임.

엔드포인트:
  GET /api/stats/verdicts  시계열 AC/SUS/failed/pending 카운트 (A)
  GET /api/stats/judges    시계열 모델별 투표 추세 + 동의율 (B)

응답은 server-side zero-fill이므로 Chart.js 등에서 series를 그대로 매핑하면 된다.
"""
from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from jcq_shared.schemas import StatsJudgeResponse, StatsVerdictResponse

from .. import backend_client
from ..admin_auth import require_admin

router = APIRouter(tags=["stats"], dependencies=[Depends(require_admin)])


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(
        status_code=e.response.status_code,
        detail=f"backend: {e.response.text[:200]}",
    )


@router.get(
    "/api/stats/verdicts",
    response_model=StatsVerdictResponse,
    summary="시계열 판정 카운트 (AC / SUS / failed / pending)",
)
async def stats_verdicts(
    bucket: Annotated[str, Query(pattern="^(hour|day|week)$")] = "day",
    since: Annotated[str | None, Query(description="ISO 8601 (UTC). 기본 = until-14일")] = None,
    until: Annotated[str | None, Query(description="ISO 8601 (UTC). 기본 = 현재")] = None,
    problem_id: Annotated[int | None, Query()] = None,
    user_id: Annotated[int | None, Query()] = None,
) -> StatsVerdictResponse:
    try:
        return backend_client.fetch_verdict_stats(
            bucket=bucket,
            since=since,
            until=until,
            problem_id=problem_id,
            user_id=user_id,
        )
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.get(
    "/api/stats/judges",
    response_model=StatsJudgeResponse,
    summary="시계열 모델별 투표 추세 — 정확성 보정 신호",
)
async def stats_judges(
    bucket: Annotated[str, Query(pattern="^(hour|day|week)$")] = "day",
    since: Annotated[str | None, Query(description="ISO 8601 (UTC). 기본 = until-14일")] = None,
    until: Annotated[str | None, Query(description="ISO 8601 (UTC). 기본 = 현재")] = None,
    problem_id: Annotated[int | None, Query()] = None,
) -> StatsJudgeResponse:
    try:
        return backend_client.fetch_judge_stats(
            bucket=bucket,
            since=since,
            until=until,
            problem_id=problem_id,
        )
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
