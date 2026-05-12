from datetime import datetime, timezone

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRow(SQLModel, table=True):
    __tablename__ = "user"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_user_provider_sub"),
    )

    id: int | None = Field(default=None, primary_key=True)

    display_name: str

    # 외부 IdP 매핑 — 학교 SSO 문서 도착 전엔 dev stub로 채움.
    # provider+external_id가 IdP의 안정적 식별자(=OIDC sub) 쌍.
    provider: str = Field(index=True)
    external_id: str = Field(index=True)
    email: str | None = None

    # 게임 상태 — 누적 AC points (효율성 multiplier 적용된 값의 합).
    # save_grading에서 첫 AC 시점에만 가산 → SubmissionRow 풀스캔 없이 리더보드 정렬 가능.
    exp: int = Field(default=0, index=True)
    # 컬럼만 두고 산정 룰은 미정. 추후 bump_user_exp 안에서 같이 갱신할 자리.
    tier: str = Field(default="bronze", index=True)

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


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

    # 출제 엔진 메타 (수동 등록 문제는 모두 NULL)
    parent_id: int | None = Field(default=None, foreign_key="problem.id", index=True)
    langsmith_trace_id: str | None = Field(default=None, index=True)
    authoring_meta: dict | None = Field(default=None, sa_column=Column(JSON))

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
    user_id: int = Field(foreign_key="user.id", index=True)
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


class TutorMessageRow(SQLModel, table=True):
    """제출당 N개 — `?regenerate=true`로 새 행이 추가됨. 이력 보존."""

    __tablename__ = "tutor_message"

    id: int | None = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="submission.id", index=True)
    message: str
    created_at: datetime = Field(default_factory=_utcnow)
