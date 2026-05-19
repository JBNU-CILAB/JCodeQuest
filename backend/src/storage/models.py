from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tz_column(*, nullable: bool = False, index: bool = False) -> Column:
    """timezone-aware DateTime 컬럼. Postgres에선 TIMESTAMPTZ, SQLite에선 TEXT로 저장된다.
    naive datetime이 들어오면 UTC로 가정해서 직렬화/역직렬화하므로 storage 경계에서
    aware/naive 가 섞여도 한쪽으로 수렴한다."""
    return Column(DateTime(timezone=True), nullable=nullable, index=index)


def iso_week_of(dt: datetime) -> str:
    """ISO 8601 주차 라벨 'YYYY-Www'. 정렬 가능한 사전식 포맷이라
    week 버킷 집계/정렬에 그대로 쓸 수 있다."""
    y, w, _ = dt.isocalendar()
    return f"{y:04d}-W{w:02d}"


def _current_iso_week() -> str:
    return iso_week_of(_utcnow())


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
    # OAuth IdP(Google 등)가 user_metadata로 넘기는 프로필 이미지 URL. 매 로그인마다
    # 최신값으로 갱신해 두고, 비어 있으면 클라이언트가 GitHub identicon으로 fallback.
    avatar_url: str | None = None

    # 사용자 커스터마이즈 필드 — OAuth 가입 직후엔 모두 NULL, /me PATCH로 채움.
    # nickname은 display_name(IdP 제공)과 별개의 표시 별명.
    nickname: str | None = None
    grade: int | None = None        # 학년 (1~6)
    department: str | None = None   # 학과/전공
    # True면 리더보드/최근 제출 등 타인에게 노출되는 모든 표면에서 display_name/avatar_url을
    # 마스킹한다. 본인 화면(/me)은 마스킹하지 않음. Supabase user_metadata.anonymous와는
    # /me PATCH 또는 로그인 시점에 동기화.
    is_anonymous: bool = Field(default=False)

    # 게임 상태 — 누적 AC points (효율성 multiplier 적용된 값의 합).
    # save_grading에서 첫 AC 시점에만 가산 → SubmissionRow 풀스캔 없이 리더보드 정렬 가능.
    exp: int = Field(default=0, index=True)
    # 컬럼만 두고 산정 룰은 미정. 추후 bump_user_exp 안에서 같이 갱신할 자리.
    tier: str = Field(default="bronze", index=True)

    # 학내 GPT(gpt.jbnu.ai) API 키 — Supabase Vault에 암호화 저장하고
    # 여기엔 vault.secrets의 UUID만 보관. 키 자체는 vault.decrypted_secrets로만 조회.
    # SQLite 테스트에선 vault가 없어 plaintext가 들어가는데, storage.vault가 동일 인터페이스로 흡수.
    api_key_secret_id: str | None = None

    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


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
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    # 출제 시점의 ISO 주차 라벨(YYYY-Www). created_at에서 파생 가능하지만 명시 컬럼으로
    # 두는 편이 인덱스 스캔 한 번에 주차 그룹핑/필터링이 끝나서 유리하다.
    iso_week: str = Field(default_factory=_current_iso_week, index=True)

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
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


class SessionRow(SQLModel, table=True):
    """서버 측 세션. 쿠키에 들어가는 token이 곧 PK.
    JWT와 달리 logout/만료가 즉시 무효화됨 — 한 row delete로 끝."""

    __tablename__ = "session"

    # secrets.token_urlsafe(32) → 약 43자. 추측 불가능한 opaque 토큰.
    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    # 만료 후 lookup이 None을 돌려주는 게이트. cleanup은 별도 purge 호출.
    expires_at: datetime = Field(sa_column=_tz_column(index=True))


class TutorMessageRow(SQLModel, table=True):
    """제출당 N개 — `?regenerate=true`로 새 행이 추가됨. 이력 보존."""

    __tablename__ = "tutor_message"

    id: int | None = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="submission.id", index=True)
    message: str
    is_user_requested: bool = Field(default=False)  # 사용자가 명시적으로 요청했는가 여부
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


class NoticeRow(SQLModel, table=True):
    """운영자 공지. 공개 read는 누구나, write/delete는 admin 토큰 보유자만."""

    __tablename__ = "notice"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    body: str
    # 상단 고정 여부 — true면 created_at 무관하게 위에 노출.
    pinned: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column(index=True))
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
