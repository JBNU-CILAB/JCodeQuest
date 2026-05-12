"""인증된 본인 프로필 + 본인 제출 이력."""
from fastapi import APIRouter, Depends, Query

from ..auth.deps import get_current_user
from ..schemas import (
    EnsembleVerdict,
    SubmissionListItem,
    SubmissionListResponse,
)
from ..storage import get_session
from ..storage.models import UserRow
from ..storage.submissions import list_user_submissions

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def me(user: UserRow = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "provider": user.provider,
        "exp": user.exp,
        "tier": user.tier,
    }


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


@router.get("/submissions", response_model=SubmissionListResponse)
def list_my_submissions(
    problem_id: int | None = Query(default=None),
    verdict: EnsembleVerdict | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserRow = Depends(get_current_user),
) -> SubmissionListResponse:
    """본인 제출 목록. 최신순.

    필터:
    - problem_id: 특정 문제만
    - verdict: AC | SUS (final_verdict 기준 — sandbox-fail은 SUS로 들어가므로 verdict=SUS에 포함)

    `code`는 응답에 포함하지 않음(페이로드 비대) — 상세는 GET /grade/{id}.
    """
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
