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
    WeeklyProblemBucket,
    WeeklyProblemBucketsResponse,
)
from ..storage import get_session
from ..storage.models import ProblemRow, UserRow
from ..storage.problems import (
    get_problem,
    list_problem_rows,
    list_week_buckets,
)
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


def _row_to_summary(row: ProblemRow) -> ProblemSummary:
    """ProblemRow에서 직접 요약을 만든다 — iso_week가 domain Problem에는 없기 때문."""
    assert row.id is not None
    return ProblemSummary(
        id=row.id,
        title=row.title,
        category=row.category,
        level=row.level,  # type: ignore[arg-type]
        points=row.points,
        one_line_summary=row.intent_rubric["one_line_summary"],
        iso_week=row.iso_week,
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
        # row를 그대로 받아 iso_week까지 요약에 실어 보낸다.
        rows = list_problem_rows(session, status="approved")
        if category is not None:
            rows = [r for r in rows if r.category == category]
        if level is not None:
            rows = [r for r in rows if r.level == level]
        return [_row_to_summary(r) for r in rows]


@router.get("/weeks", response_model=WeeklyProblemBucketsResponse)
def list_weekly_buckets() -> WeeklyProblemBucketsResponse:
    """approved 문제를 출제 주차별로 묶어 '주차/문제수' 인덱스를 돌려준다.
    내림차순(최신 주가 먼저) — 별도 정렬 옵션은 사용 빈도가 낮아 추가하지 않음."""
    with get_session() as session:
        rows = list_week_buckets(session, status="approved")
    return WeeklyProblemBucketsResponse(
        buckets=[
            WeeklyProblemBucket(week=week, count=count)
            for week, count in rows
        ]
    )


@router.get("/weeks/{week}", response_model=list[ProblemSummary])
def list_problems_in_week(week: str) -> list[ProblemSummary]:
    """특정 주차('YYYY-Www')의 approved 문제 요약 목록."""
    with get_session() as session:
        rows = list_problem_rows(
            session, status="approved", iso_week=week
        )
    return [_row_to_summary(r) for r in rows]


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


