from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth.deps import get_current_user
from ..schemas import (
    AttemptStatusResponse,
    EnsembleVerdict,
    Problem,
    ProblemDetail,
    ProblemLevel,
    ProblemSummary,
    PublicTestCase,
    SubmissionListItem,
    SubmissionListResponse,
)
from ..storage import get_session
from ..storage.models import ProblemRow, UserRow
from ..storage.problems import get_problem, list_problems
from ..storage.submissions import (
    MAX_ATTEMPTS,
    attempt_status,
    list_user_submissions,
)

router = APIRouter(prefix="/problems", tags=["problems"])


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


def _to_summary(p: Problem) -> ProblemSummary:
    return ProblemSummary(
        id=p.id,
        title=p.title,
        category=p.category,
        level=p.level,
        points=p.points,
        one_line_summary=p.intent_rubric.one_line_summary,
    )


def _to_detail(p: Problem) -> ProblemDetail:
    return ProblemDetail(
        id=p.id,
        title=p.title,
        statement=p.statement,
        category=p.category,
        level=p.level,
        points=p.points,
        time_limit_ms=p.time_limit_ms,
        memory_limit_mb=p.memory_limit_mb,
        one_line_summary=p.intent_rubric.one_line_summary,
        sample_test_cases=[
            PublicTestCase(
                ordinal=t.ordinal,
                stdin=t.stdin,
                expected_stdout=t.expected_stdout,
            )
            for t in p.test_cases
            if t.is_sample
        ],
    )


@router.get("", response_model=list[ProblemSummary])
def list_approved_problems(
    category: str | None = Query(default=None),
    level: ProblemLevel | None = Query(default=None),
) -> list[ProblemSummary]:
    with get_session() as session:
        problems = list_problems(
            session, status="approved", category=category, level=level
        )
    return [_to_summary(p) for p in problems]


@router.get("/{problem_id}", response_model=ProblemDetail)
def get_problem_detail(problem_id: int) -> ProblemDetail:
    with get_session() as session:
        row = session.get(ProblemRow, problem_id)
        if row is None or row.status != "approved":
            raise HTTPException(404, f"problem {problem_id} not found")
        problem = get_problem(session, problem_id)
    assert problem is not None
    return _to_detail(problem)


@router.get(
    "/{problem_id}/attempt-status", response_model=AttemptStatusResponse
)
def get_attempt_status(
    problem_id: int,
    user: UserRow = Depends(get_current_user),
) -> AttemptStatusResponse:
    """제출 화면이 버튼 활성화/비활성화를 결정하기 위해 호출.
    이미 푼 문제거나 시도 초과면 can_submit=False — 쿨다운 중이면 남은 초가 양수."""
    assert user.id is not None
    with get_session() as session:
        row = session.get(ProblemRow, problem_id)
        if row is None or row.status != "approved":
            raise HTTPException(404, f"problem {problem_id} not found")
        st = attempt_status(session, user.id, problem_id)
    return AttemptStatusResponse(
        problem_id=problem_id,
        attempts=st.attempts,
        remaining=st.remaining,
        max_attempts=MAX_ATTEMPTS,
        solved=st.solved,
        cooldown_remaining_s=st.cooldown_remaining_s(),
        can_submit=st.can_submit and st.cooldown_remaining_s() <= 0,
    )


@router.get(
    "/{problem_id}/my-submissions", response_model=SubmissionListResponse
)
def list_my_submissions_for_problem(
    problem_id: int,
    verdict: EnsembleVerdict | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserRow = Depends(get_current_user),
) -> SubmissionListResponse:
    """문제 페이지에서 '내가 이 문제에 낸 시도들'을 보여주기 위한 편의 엔드포인트."""
    assert user.id is not None
    with get_session() as session:
        row = session.get(ProblemRow, problem_id)
        if row is None or row.status != "approved":
            raise HTTPException(404, f"problem {problem_id} not found")
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
