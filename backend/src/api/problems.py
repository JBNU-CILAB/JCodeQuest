from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    Problem,
    ProblemDetail,
    ProblemLevel,
    ProblemSummary,
    PublicTestCase,
)
from ..storage import get_session
from ..storage.models import ProblemRow
from ..storage.problems import get_problem, list_problems

router = APIRouter(prefix="/problems", tags=["problems"])


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
