from sqlalchemy import func
from sqlmodel import Session, select

from ..schemas import IntentRubric, Problem, TestCase
from .models import ProblemRow, TestCaseRow


def _to_domain(row: ProblemRow) -> Problem:
    return Problem(
        id=row.id,  # type: ignore[arg-type]
        title=row.title,
        statement=row.statement,
        category=row.category,
        level=row.level,  # type: ignore[arg-type]
        points=row.points,
        time_limit_ms=row.time_limit_ms,
        memory_limit_mb=row.memory_limit_mb,
        reference_code=row.reference_code,
        intent_rubric=IntentRubric.model_validate(row.intent_rubric),
        test_cases=[
            TestCase(
                ordinal=t.ordinal,
                stdin=t.stdin,
                expected_stdout=t.expected_stdout,
                is_sample=t.is_sample,
            )
            for t in row.test_cases
        ],
    )


def get_problem(session: Session, problem_id: int) -> Problem | None:
    row = session.get(ProblemRow, problem_id)
    return _to_domain(row) if row else None


def list_problems(
    session: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    level: str | None = None,
    iso_week: str | None = None,
) -> list[Problem]:
    stmt = select(ProblemRow)
    if status is not None:
        stmt = stmt.where(ProblemRow.status == status)
    if category is not None:
        stmt = stmt.where(ProblemRow.category == category)
    if level is not None:
        stmt = stmt.where(ProblemRow.level == level)
    if iso_week is not None:
        stmt = stmt.where(ProblemRow.iso_week == iso_week)
    return [_to_domain(r) for r in session.exec(stmt).all()]


def list_problem_rows(
    session: Session,
    *,
    status: str | None = None,
    iso_week: str | None = None,
) -> list[ProblemRow]:
    """row-level 메타(iso_week, created_at)를 그대로 써야 하는 라우터용.
    list_problems는 Problem(shared) 도메인 객체만 돌려주는데 거기에는 주차 컬럼이 없다."""
    stmt = select(ProblemRow)
    if status is not None:
        stmt = stmt.where(ProblemRow.status == status)
    if iso_week is not None:
        stmt = stmt.where(ProblemRow.iso_week == iso_week)
    return list(session.exec(stmt).all())


def list_week_buckets(
    session: Session, *, status: str | None = None
) -> list[tuple[str, int]]:
    """주차별 (week, count)을 ISO 주차 내림차순(최신주가 위)으로 반환."""
    stmt = select(ProblemRow.iso_week, func.count(ProblemRow.id))
    if status is not None:
        stmt = stmt.where(ProblemRow.status == status)
    stmt = stmt.group_by(ProblemRow.iso_week).order_by(
        ProblemRow.iso_week.desc()
    )
    return [(week, count) for week, count in session.exec(stmt).all()]


def create_problem(
    session: Session,
    problem: Problem,
    *,
    status: str = "draft",
    parent_id: int | None = None,
    langsmith_trace_id: str | None = None,
    authoring_meta: dict | None = None,
    iso_week: str | None = None,
) -> int:
    # 출제 주차는 호출자가 명시할 수 있고, 생략 시 ProblemRow.default_factory가
    # 현재 UTC 주차를 박는다(출제 엔진은 명시 전달 — persist 노드/manual create 참조).
    row_kwargs: dict = {}
    if iso_week is not None:
        row_kwargs["iso_week"] = iso_week
    row = ProblemRow(
        title=problem.title,
        statement=problem.statement,
        category=problem.category,
        level=problem.level,
        points=problem.points,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
        reference_code=problem.reference_code,
        intent_rubric=problem.intent_rubric.model_dump(),
        status=status,
        parent_id=parent_id,
        langsmith_trace_id=langsmith_trace_id,
        authoring_meta=authoring_meta,
        **row_kwargs,
        test_cases=[
            TestCaseRow(
                ordinal=t.ordinal,
                stdin=t.stdin,
                expected_stdout=t.expected_stdout,
                is_sample=t.is_sample,
            )
            for t in problem.test_cases
        ],
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    assert row.id is not None
    return row.id
