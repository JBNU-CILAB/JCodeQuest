from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProblemRow(SQLModel, table=True):
    __tablename__ = "problem"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    statement: str
    category: str
    level: str = "bronze"
    points: int = 100
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256
    reference_code: str
    intent_rubric: dict = Field(sa_column=Column(JSON, nullable=False))
    status: str = Field(default="draft", index=True)  # draft | approved | retired
    created_at: datetime = Field(default_factory=_utcnow)

    test_cases: list["TestCaseRow"] = Relationship(
        back_populates="problem",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "TestCaseRow.ordinal",
        },
    )


class TestCaseRow(SQLModel, table=True):
    __tablename__ = "test_case"

    id: int | None = Field(default=None, primary_key=True)
    problem_id: int = Field(foreign_key="problem.id", index=True)
    ordinal: int
    stdin: str
    expected_stdout: str
    is_sample: bool = False

    problem: ProblemRow | None = Relationship(back_populates="test_cases")


class SubmissionRow(SQLModel, table=True):
    __tablename__ = "submission"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    problem_id: int = Field(foreign_key="problem.id", index=True)
    code: str
    status: str = Field(default="queued", index=True)  # queued|running|done|failed
    final_verdict: str | None = None        # "AC" | "SUS"
    mode: str | None = None                 # "unanimous" | "majority"
    votes: list | None = Field(default=None, sa_column=Column(JSON))
    test_results: list | None = Field(default=None, sa_column=Column(JSON))
    max_elapsed_ms: int | None = None
    peak_memory_kb: int | None = None
    points_awarded: int | None = None       # AC인 경우에만 채워짐
    created_at: datetime = Field(default_factory=_utcnow)
