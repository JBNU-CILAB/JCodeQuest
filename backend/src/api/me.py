"""인증된 본인 프로필 + 본인 제출 이력."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..auth.deps import get_current_user
from ..schemas import (
    EnsembleVerdict,
    MeResponse,
    SubmissionListItem,
    SubmissionListResponse,
)
from ..storage import get_session
from ..storage.models import UserRow
from ..storage.submissions import list_user_submissions

router = APIRouter(prefix="/me", tags=["me"])


@router.get(
    "",
    response_model=MeResponse,
    summary="내 프로필 조회",
    description="현재 세션의 사용자 프로필을 반환한다.",
    responses={401: {"description": "유효한 세션 쿠키 없음"}},
)
def me(user: UserRow = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,  # type: ignore[arg-type]
        display_name=user.display_name,
        email=user.email,
        provider=user.provider,  # type: ignore[arg-type]
        exp=user.exp,
        tier=user.tier,
    )


def _to_submission_item(row) -> SubmissionListItem:
    return SubmissionListItem(
        id=row.id,
        problem_id=row.problem_id,
        status=row.status,
        final_verdict=row.final_verdict,
        mode=row.mode,
        points_awarded=row.points_awarded,
        max_elapsed_ms=row.max_elapsed_ms,
        peak_memory_kb=row.peak_memory_kb,
        created_at=row.created_at,
    )


@router.get(
    "/submissions",
    response_model=SubmissionListResponse,
    summary="내 제출 목록",
    description=(
        "본인이 낸 제출들을 최신순으로 반환한다. "
        "`code` 필드는 페이로드 비대해서 제외 — 상세는 `GET /grade/{id}`."
    ),
    responses={401: {"description": "유효한 세션 쿠키 없음"}},
)
def list_my_submissions(
    problem_id: Annotated[
        int | None, Query(description="특정 문제로 필터")
    ] = None,
    verdict: Annotated[
        EnsembleVerdict | None,
        Query(
            description=(
                "AC | SUS. sandbox-fail은 final_verdict=SUS로 들어가므로 "
                "verdict=SUS에 포함된다."
            )
        ),
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="페이지 크기 (1–100)")
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="오프셋")] = 0,
    user: UserRow = Depends(get_current_user),
) -> SubmissionListResponse:
    assert user.id is not None
    with get_session() as session:
        rows, total = list_user_submissions(
            session,
            user.id,
            problem_id=problem_id,
            verdict=verdict,
            limit=limit,
            offset=offset,
        )
        items = [_to_submission_item(r) for r in rows]
    return SubmissionListResponse(
        items=items, total=total, limit=limit, offset=offset
    )
