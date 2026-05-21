"""공개 최근 제출 목록 — 인증 불필요.

display_name과 문제 title만 노출하므로 리더보드와 동일한 노출 정책을 따른다.
코드/votes/test_results 등 본문은 포함하지 않는다.
"""
from typing import Annotated

from fastapi import APIRouter, Query

from ..schemas import RecentSubmissionItem, RecentSubmissionsResponse
from ..storage import get_session
from ..storage.submissions import list_recent_submissions

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get(
    "/recent",
    response_model=RecentSubmissionsResponse,
    summary="전체 사용자 최근 제출",
    description=(
        "모든 사용자의 최근 제출을 created_at DESC 순으로 반환한다. "
        "display_name과 문제 title만 노출하고 code/votes는 포함하지 않는다."
    ),
)
def get_recent_submissions(
    limit: Annotated[
        int, Query(ge=1, le=50, description="가져올 건수 (1~50)")
    ] = 20,
) -> RecentSubmissionsResponse:
    with get_session() as session:
        rows = list_recent_submissions(session, limit=limit)
    items = [
        RecentSubmissionItem(
            id=s.id,  # type: ignore[arg-type]
            user_id=s.user_id,
            user_display_name=name,
            problem_id=s.problem_id,
            problem_title=title,
            status=s.status,  # type: ignore[arg-type]
            final_verdict=s.final_verdict,  # type: ignore[arg-type]
            mode=s.mode,  # type: ignore[arg-type]
            points_awarded=s.points_awarded,
            max_elapsed_ms=s.max_elapsed_ms,
            peak_memory_kb=s.peak_memory_kb,
            created_at=s.created_at,
        )
        for (s, name, title) in rows
    ]
    return RecentSubmissionsResponse(items=items, limit=limit)
