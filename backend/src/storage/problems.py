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
    session: Session, *, status: str | None = None, category: str | None = None
) -> list[Problem]:
    stmt = select(ProblemRow)
    if status is not None:
        stmt = stmt.where(ProblemRow.status == status)
    if category is not None:
        stmt = stmt.where(ProblemRow.category == category)
    return [_to_domain(r) for r in session.exec(stmt).all()]


def create_problem(session: Session, problem: Problem, *, status: str = "draft") -> int:
    row = ProblemRow(
        title=problem.title,
        statement=problem.statement,
        category=problem.category,
        level=problem.level,
        reference_code=problem.reference_code,
        intent_rubric=problem.intent_rubric.model_dump(),
        status=status,
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
