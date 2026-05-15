"""제출(풀이 기록) 조회 라우터 — backend /internal/submissions 위임.

채점 결과를 admin_dashboard에 노출하는 엔드포인트. authoring_engine에서 옮겨옴.
"""
from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from jcq_shared.schemas import AdminSubmissionDetail, AdminSubmissionSummary

from .. import backend_client
from ..admin_auth import require_admin

router = APIRouter(tags=["submissions"], dependencies=[Depends(require_admin)])


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(
        status_code=e.response.status_code,
        detail=f"backend: {e.response.text[:200]}",
    )


@router.get(
    "/api/submissions",
    response_model=list[AdminSubmissionSummary],
    summary="제출 목록 (필터 + 페이지네이션)",
)
async def list_submissions(
    user_id: Annotated[int | None, Query(description="해당 유저의 제출만")] = None,
    problem_id: Annotated[int | None, Query(description="해당 문제의 제출만")] = None,
    verdict: Annotated[str | None, Query(description="AC | SUS")] = None,
    status: Annotated[str | None, Query(description="queued | running | done | failed")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminSubmissionSummary]:
    try:
        return backend_client.list_submissions(
            user_id=user_id,
            problem_id=problem_id,
            verdict=verdict,
            status=status,
            limit=limit,
            offset=offset,
        )
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.get(
    "/api/submissions/{submission_id}",
    response_model=AdminSubmissionDetail,
    summary="제출 상세 (코드/votes/test_results 포함)",
    responses={404: {"description": "제출 없음"}},
)
async def get_submission(
    submission_id: Annotated[int, PathParam(description="제출 ID")],
) -> AdminSubmissionDetail:
    try:
        return backend_client.get_submission(submission_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
