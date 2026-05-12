from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

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

ProblemIdPath = Annotated[int, Path(description="문제 ID", examples=[1])]

_NOT_FOUND_OR_NOT_APPROVED = {
    404: {"description": "문제가 없거나 status != 'approved'"}
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


@router.get(
    "",
    response_model=list[ProblemSummary],
    summary="승인된 문제 목록",
    description="status='approved' 문제만 노출. category/level로 필터링 가능.",
)
def list_approved_problems(
    category: Annotated[
        str | None, Query(description="카테고리 슬러그로 필터")
    ] = None,
    level: Annotated[
        ProblemLevel | None, Query(description="난이도 필터")
    ] = None,
) -> list[ProblemSummary]:
    with get_session() as session:
        problems = list_problems(
            session, status="approved", category=category, level=level
        )
    return [_to_summary(p) for p in problems]


@router.get(
    "/{problem_id}",
    response_model=ProblemDetail,
    summary="문제 상세 (공개 정보)",
    description=(
        "statement와 sample test case만 노출한다. "
        "reference_code/intent_rubric/hidden case는 응답에 포함되지 않는다."
    ),
    responses=_NOT_FOUND_OR_NOT_APPROVED,
)
def get_problem_detail(problem_id: ProblemIdPath) -> ProblemDetail:
    with get_session() as session:
        row = session.get(ProblemRow, problem_id)
        if row is None or row.status != "approved":
            raise HTTPException(404, f"problem {problem_id} not found")
        problem = get_problem(session, problem_id)
    assert problem is not None
    return _to_detail(problem)


@router.get(
    "/{problem_id}/attempt-status",
    response_model=AttemptStatusResponse,
    summary="시도 가능 여부 확인",
    description=(
        "제출 화면이 버튼 활성/비활성을 결정하기 위해 호출. "
        "이미 풀었거나 시도 초과면 can_submit=False, 쿨다운 중이면 cooldown_remaining_s>0."
    ),
    responses={
        401: {"description": "유효한 세션 쿠키 없음"},
        **_NOT_FOUND_OR_NOT_APPROVED,
    },
)
def get_attempt_status(
    problem_id: ProblemIdPath,
    user: UserRow = Depends(get_current_user),
) -> AttemptStatusResponse:
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
    "/{problem_id}/my-submissions",
    response_model=SubmissionListResponse,
    summary="이 문제에 낸 내 제출들",
    description="`/me/submissions` 와 동일하지만 problem_id가 경로로 고정.",
    responses={
        401: {"description": "유효한 세션 쿠키 없음"},
        **_NOT_FOUND_OR_NOT_APPROVED,
    },
)
def list_my_submissions_for_problem(
    problem_id: ProblemIdPath,
    verdict: Annotated[
        EnsembleVerdict | None, Query(description="AC|SUS 필터")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: UserRow = Depends(get_current_user),
) -> SubmissionListResponse:
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
