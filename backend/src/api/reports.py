"""사용자 버그 제보 라우터. Supabase Bearer JWT 인증 — 본인 user_id로 귀속.

관리자 조회/처리는 별도로 `/internal/reports`에서 노출 (admin_dashboard 경유).
"""
from fastapi import APIRouter, Depends, HTTPException

from ..auth.deps import get_current_user
from ..schemas import BugReportCreateRequest, BugReportCreateResponse
from ..storage import get_session
from ..storage.bug_reports import create_bug_report
from ..storage.models import ProblemRow, UserRow

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post(
    "",
    response_model=BugReportCreateResponse,
    summary="버그/문제 제보 등록",
    description=(
        "Solver 화면의 '버그 제보' 버튼에서 호출. problem_id는 옵션 — "
        "system/other 카테고리는 특정 문제 없이 등록 가능. code_snapshot은 "
        "사용자가 '현재 코드 첨부'를 켰을 때만 보냄."
    ),
    responses={
        401: {"description": "인증 필요"},
        404: {"description": "problem_id 지정했으나 문제 없음"},
        422: {"description": "검증 실패 (title/body 길이 등)"},
    },
)
def create_report(
    payload: BugReportCreateRequest,
    user: UserRow = Depends(get_current_user),
) -> BugReportCreateResponse:
    assert user.id is not None
    with get_session() as session:
        # problem_id가 주어졌다면 실재 여부 확인 — FK는 PostgreSQL/SQLite 모두 강제하지만,
        # 친절한 404를 응답에 싣기 위해 명시적으로 한 번 더 체크.
        if payload.problem_id is not None:
            if session.get(ProblemRow, payload.problem_id) is None:
                raise HTTPException(404, f"problem {payload.problem_id} not found")

        row = create_bug_report(
            session,
            user_id=user.id,
            problem_id=payload.problem_id,
            category=payload.category,
            title=payload.title.strip(),
            body=payload.body.strip(),
            code_snapshot=payload.code_snapshot,
        )
    assert row.id is not None
    return BugReportCreateResponse(id=row.id, status="open")  # type: ignore[arg-type]
