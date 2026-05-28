from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from jcq_shared.schemas import (
    AdminSubmissionDetail,
    AdminSubmissionSummary,
    AdminUserSummary,
    AuthoringProblemAdmin,
    AuthoringProblemCreate,
    AuthoringProblemCreateResponse,
    AuthoringProblemSummary,
    AuthoringProblemUpdate,
    AuthoringTestCase,
    EmbeddingUpdateRequest,
    EnsembleMode,
    EnsembleResult,
    EnsembleVerdict,
    ExecResult,
    ExecStatus,
    GradeEvent,
    GradeEventType,
    GradeSubmitRequest,
    IntentRubric,
    ProblemEmbedding,
    JudgeVote,
    JudgeVotePartial,
    Problem,
    ProblemDeleteCascade,
    ProblemDeleteResponse,
    ProblemLevel,
    RunCreate,
    RunDetail,
    RunNodeState,
    RunSummary,
    RunUpdate,
    StatsBucket,
    StatsJudgeBucket,
    StatsJudgeBucketEntry,
    StatsJudgeResponse,
    StatsVerdictBucket,
    StatsVerdictResponse,
    TestCase,
    TestResult,
    UserDeleteCascade,
    UserDeleteResponse,
    Verdict,
)

__all__ = [
    "AdminSubmissionDetail",
    "AdminSubmissionSummary",
    "AdminUserSummary",
    "AuthoringProblemAdmin",
    "AuthoringProblemCreate",
    "AuthoringProblemCreateResponse",
    "AuthoringProblemSummary",
    "AuthoringProblemUpdate",
    "AuthoringTestCase",
    "EmbeddingUpdateRequest",
    "EnsembleMode",
    "EnsembleResult",
    "EnsembleVerdict",
    "ExecResult",
    "ExecStatus",
    "GradeEvent",
    "GradeEventType",
    "GradeSubmitRequest",
    "IntentRubric",
    "JudgeVote",
    "JudgeVotePartial",
    "Problem",
    "ProblemDeleteCascade",
    "ProblemDeleteResponse",
    "ProblemEmbedding",
    "ProblemLevel",
    "RunCreate",
    "RunDetail",
    "RunNodeState",
    "RunSummary",
    "RunUpdate",
    "StatsBucket",
    "StatsJudgeBucket",
    "StatsJudgeBucketEntry",
    "StatsJudgeResponse",
    "StatsVerdictBucket",
    "StatsVerdictResponse",
    "TestCase",
    "TestResult",
    "UserDeleteCascade",
    "UserDeleteResponse",
    "Verdict",
]


class Submission(BaseModel):
    id: int
    user_id: int
    problem_id: int
    code: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


JobStatus = Literal["queued", "running", "done", "failed"]

# 제출 코드 길이 상한 — 알고리즘 풀이는 통상 수 KB. 페이로드 폭주로 DB·메모리를 흔드는
# 케이스 차단. 변경 시 storage.submissions.MAX_ATTEMPTS와 무관.
MAX_CODE_LENGTH = 64 * 1024


class GradeRequest(BaseModel):
    """user_id는 인증된 세션에서 추출 — body로 받지 않음(위조 차단)."""

    problem_id: int = Field(description="채점할 문제 ID", examples=[1])
    code: str = Field(
        min_length=1,
        max_length=MAX_CODE_LENGTH,
        description="제출할 Python 소스 — UTF-8, 최대 64 KiB",
        examples=["n = int(input())\nprint(n * 2)\n"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "problem_id": 1,
                    "code": "n = int(input())\nprint(n * 2)\n",
                }
            ]
        }
    )


class GradeAcceptedResponse(BaseModel):
    submission_id: int = Field(
        description="생성된 제출 ID — 이후 /grade/{id} 또는 SSE에서 사용",
        examples=[42],
    )
    status: JobStatus = Field(
        default="queued", description="제출 직후 상태 — 항상 queued"
    )


class SubmissionStatusResponse(BaseModel):
    submission_id: int = Field(examples=[42])
    status: JobStatus = Field(description="채점 진행 상태")
    final_verdict: EnsembleVerdict | None = Field(
        default=None, description="채점 완료 후의 최종 판정 (status=done일 때만)"
    )
    test_results: list[TestResult] | None = Field(
        default=None, description="테스트 케이스별 결과 — sandbox 실행 후 채워짐"
    )
    ensemble: EnsembleResult | None = Field(
        default=None,
        description="3-judge 앙상블 결과 — 모든 케이스 통과 시에만 채워짐",
    )
    points_awarded: int | None = Field(
        default=None,
        description="첫 AC일 때 사용자 EXP에 가산된 점수. 그 외엔 0 또는 None.",
        examples=[100],
    )


class PublicTestCase(BaseModel):
    """학생에게 노출되는 샘플 케이스. hidden 케이스의 stdin/expected는 절대 포함하지 않음."""

    ordinal: int = Field(description="테스트 순번", examples=[1])
    stdin: str = Field(description="표준입력 (개행 포함)")
    expected_stdout: str = Field(description="기대 표준출력 (개행 trim)")


class ProblemSummary(BaseModel):
    """목록용 — reference_code / intent_rubric 내부는 제외."""

    id: int = Field(examples=[1])
    title: str = Field(description="문제 제목", examples=["두 배 출력"])
    category: str = Field(description="카테고리 슬러그", examples=["basic"])
    level: Literal["bronze", "silver", "gold"] = Field(
        description="난이도"
    )
    points: int = Field(
        description="기본 배점 — 첫 AC 시 EXP로 가산 (효율 보너스 별도)",
        examples=[100],
    )
    one_line_summary: str = Field(description="한 줄 요약")
    iso_week: str = Field(
        description=(
            "출제 주차 라벨 'YYYY-Www' (ISO 8601). "
            "주차별 화면이 한 번의 목록 응답으로 라벨까지 그릴 수 있게 포함."
        ),
        examples=["2026-W19"],
    )


class WeeklyProblemBucket(BaseModel):
    """주차 인덱스 — 'YYYY-Www'와 그 주에 출제된 approved 문제 수."""

    week: str = Field(
        description="ISO 8601 주차 라벨 'YYYY-Www'", examples=["2026-W19"]
    )
    count: int = Field(
        description="해당 주에 출제된 approved 문제 수", examples=[3]
    )


class WeeklyProblemBucketsResponse(BaseModel):
    buckets: list[WeeklyProblemBucket] = Field(
        description="ISO 주차 내림차순(최신 주가 먼저) 정렬"
    )


class ProblemDetail(BaseModel):
    """상세 — statement와 샘플 케이스만 공개. 채점 기준/정답 코드는 비공개."""

    id: int
    title: str
    statement: str = Field(description="문제 본문 (Markdown 허용)")
    category: str
    level: Literal["bronze", "silver", "gold"]
    points: int
    time_limit_ms: int = Field(description="실행 시간 제한 (ms)", examples=[2000])
    memory_limit_mb: int = Field(
        description="메모리 제한 (MB)", examples=[256]
    )
    one_line_summary: str
    sample_test_cases: list[PublicTestCase] = Field(
        default_factory=list,
        description="공개 샘플 케이스 — hidden 케이스는 포함하지 않음",
    )


class AttemptStatusResponse(BaseModel):
    """제출 화면이 '남은 시도 횟수 / 쿨다운 / AC 여부'를 한 번에 보고 그릴 수 있도록 묶음."""

    problem_id: int
    attempts: int = Field(description="누적 제출 횟수", examples=[2])
    remaining: int = Field(
        description="남은 시도 횟수 (max_attempts - attempts)", examples=[8]
    )
    max_attempts: int = Field(description="문제당 최대 시도 횟수", examples=[10])
    solved: bool = Field(description="이미 AC를 받은 적이 있는지")
    cooldown_remaining_s: float = Field(
        description="다음 제출까지 남은 쿨다운 초. 0 이하면 즉시 가능."
    )
    can_submit: bool = Field(
        description="현재 시점에 제출 가능 여부 (solved=False & remaining>0 & cooldown<=0)"
    )


class SubmissionListItem(BaseModel):
    """본인 제출 목록용 — code는 페이로드 비대해서 제외. 상세는 /grade/{id}로."""

    id: int = Field(description="제출 ID")
    problem_id: int
    status: JobStatus
    final_verdict: EnsembleVerdict | None = None
    mode: EnsembleMode | None = Field(
        default=None,
        description="앙상블 모드 (unanimous|majority). 앙상블 미실행이면 null.",
    )
    points_awarded: int | None = None
    max_elapsed_ms: int | None = Field(
        default=None, description="모든 케이스 중 최대 실행 시간 (ms)"
    )
    peak_memory_kb: int | None = Field(
        default=None, description="모든 케이스 중 최대 메모리 (KB)"
    )
    created_at: datetime


class SubmissionListResponse(BaseModel):
    items: list[SubmissionListItem]
    total: int = Field(description="필터 적용 후 전체 건수")
    limit: int
    offset: int


class RecentSubmissionItem(BaseModel):
    """공개 최근 제출 — 코드/votes 미노출, display_name/문제 title만 포함."""

    id: int = Field(description="제출 ID")
    user_id: int
    user_display_name: str | None = None
    problem_id: int
    problem_title: str | None = None
    status: JobStatus
    final_verdict: EnsembleVerdict | None = None
    mode: EnsembleMode | None = None
    points_awarded: int | None = None
    max_elapsed_ms: int | None = None
    peak_memory_kb: int | None = None
    created_at: datetime


class RecentSubmissionsResponse(BaseModel):
    items: list[RecentSubmissionItem]
    limit: int


class DailySolve(BaseModel):
    date: str = Field(description="KST 날짜 (YYYY-MM-DD)")
    count: int = Field(description="그 날 처음 AC한 문제 수")


class StreakResponse(BaseModel):
    """GET /me/streak — '새 문제를 처음 AC한 날' 기준 연속 일수.

    날짜 경계는 KST(UTC+9)로 계산. 오늘 또는 어제까지 이어진 연속이면 current가 유지되고,
    그보다 더 오래 끊겼다면 current=0이 된다. daily_solves는 잔디 시각화를 위한 최근 window 일치
    일별 새 문제 풀이 수 (오래된 → 최신 순).
    """

    current_streak: int = Field(description="현재 연속 일수")
    longest_streak: int = Field(description="역대 최장 연속 일수")
    last_solved_date: str | None = Field(
        default=None,
        description="가장 최근에 새 문제를 푼 날 (KST, YYYY-MM-DD). 미해결이면 null.",
    )
    daily_solves: list[DailySolve] = Field(
        default_factory=list,
        description="최근 window 일치 일별 새 문제 풀이 수. 오래된 날짜부터 정렬.",
    )


class MeResponse(BaseModel):
    """GET /me 의 응답 — UserRow의 공개 가능한 필드만."""

    id: int = Field(examples=[1])
    display_name: str = Field(examples=["김민석"])
    email: str = Field(examples=["foo@jbnu.ac.kr"])
    provider: Literal["google", "dev_stub", "supabase"] = Field(
        description="인증 공급자"
    )
    exp: int = Field(description="누적 경험치", examples=[1500])
    tier: str = Field(description="현재 티어 (exp 기반 산출)")
    has_api_key: bool = Field(
        default=False,
        description="본인 학내 GPT API 키 등록 여부. 키 값 자체는 응답에 포함하지 않는다.",
    )
    nickname: str | None = Field(
        default=None,
        description="사용자가 직접 설정한 별명. 미설정이면 null.",
        examples=["민석"],
    )
    grade: int | None = Field(
        default=None,
        ge=1,
        le=6,
        description="학년 (1~6). 미설정이면 null.",
        examples=[3],
    )
    department: str | None = Field(
        default=None,
        description="학과/전공. 미설정이면 null.",
        examples=["컴퓨터공학부"],
    )
    is_anonymous: bool = Field(
        default=False,
        description=(
            "True면 리더보드/최근 제출 등 타인에게 노출되는 화면에서 "
            "display_name과 avatar_url을 마스킹한다. 본인 /me 응답은 마스킹하지 않음."
        ),
    )
    avatar_url: str | None = Field(
        default=None,
        description=(
            "현재 사용자에게 보일 프로필 이미지 URL. 사용자가 직접 업로드한 커스텀 "
            "이미지를 우선 저장하며, 비어 있으면 클라이언트가 identicon으로 fallback."
        ),
    )


class PublicProfileStats(BaseModel):
    """공개 프로필의 활동 요약 — is_anonymous=False일 때만 채워진다."""

    solved: int = Field(description="해결한 distinct 문제 수")
    total_submissions: int = Field(description="총 제출 수")
    current_streak: int = Field(description="현재 연속 풀이 일수")
    longest_streak: int = Field(description="역대 최장 연속 일수")
    daily_solves: list[DailySolve] = Field(
        default_factory=list,
        description="잔디 시각화용 일별 새 문제 풀이 수 (오래된 → 최신 순).",
    )


class PublicProfileResponse(BaseModel):
    """GET /users/{id} — 타인에게 노출되는 공개 프로필.

    is_anonymous=True면 display_name(닉네임/'익명')·tier·exp만 채우고 나머지 필드는
    서버가 None으로 비워서 내려준다(프론트 마스킹이 아니라 서버 측 마스킹).
    이메일/API 키 등 민감 필드는 익명 여부와 무관하게 절대 포함하지 않는다.
    """

    user_id: int = Field(examples=[1])
    display_name: str = Field(
        description="익명이면 닉네임(없으면 '익명'), 아니면 실명"
    )
    tier: str = Field(description="현재 티어")
    exp: int = Field(description="누적 경험치")
    is_anonymous: bool = Field(
        description="True면 프론트가 축약 레이아웃(닉네임+티어+EXP)을 렌더한다."
    )
    avatar_url: str | None = Field(
        default=None, description="프로필 이미지 URL. 익명이면 항상 null."
    )
    grade: int | None = Field(default=None, description="학년. 익명이면 항상 null.")
    department: str | None = Field(
        default=None, description="학과. 익명이면 항상 null."
    )
    rank: int | None = Field(
        default=None,
        description="누적 EXP 기준 전체 순위(1-base). exp=0이거나 익명이면 null.",
    )
    stats: PublicProfileStats | None = Field(
        default=None, description="활동 요약. 익명이면 null."
    )


class ProfileUpdateRequest(BaseModel):
    """PATCH /me — 학년/학과/닉네임/익명여부/아바타 URL 부분 갱신.
    필드를 생략하면 미변경, null을 명시하면 해당 필드를 비운다(is_anonymous는 null 불가)."""

    model_config = ConfigDict(extra="forbid")

    nickname: str | None = Field(
        default=None,
        max_length=32,
        description="별명 (최대 32자). null이면 기존 값을 비운다.",
        examples=["민석"],
    )
    grade: int | None = Field(
        default=None,
        ge=1,
        le=6,
        description="학년 1~6. null이면 기존 값을 비운다.",
        examples=[3],
    )
    department: str | None = Field(
        default=None,
        max_length=100,
        description="학과/전공 (최대 100자). null이면 기존 값을 비운다.",
        examples=["컴퓨터공학부"],
    )
    is_anonymous: bool | None = Field(
        default=None,
        description=(
            "익명 표시 토글. true/false 명시 시에만 갱신, 생략(null)이면 미변경. "
            "True면 타인에게 노출되는 화면에서 display_name/avatar_url이 마스킹된다."
        ),
    )
    avatar_url: str | None = Field(
        default=None,
        max_length=1024,
        description=(
            "프로필 이미지 URL. 사용자가 Supabase Storage에 업로드한 공개 URL을 "
            "그대로 저장한다. null을 명시하면 DB의 avatar_url을 비워서 리더보드 등에서 "
            "identicon fallback이 적용된다. 생략 시 미변경."
        ),
    )


_API_KEY_PATTERN = r"^[!-~]{20,512}$"
"""인쇄 가능 ASCII(스페이스 제외)로만 구성된 20–512자 문자열.
학내 GPT 게이트웨이 키 형식이 공개되지 않아 prefix 강제는 피하고, 사용자가
복사 시 섞이기 쉬운 공백/개행/탭/유니코드 문자만 차단한다. 너무 짧은 placeholder
(예: 'test')도 함께 막는다."""


class ApiKeyUpdateRequest(BaseModel):
    """PUT /me/api-key — 학내 GPT API 키 등록/갱신."""

    api_key: str = Field(
        min_length=20,
        max_length=512,
        pattern=_API_KEY_PATTERN,
        description=(
            "등록할 API 키 (학내 GPT 게이트웨이 발급). "
            "공백·개행 없는 인쇄 가능 ASCII 20–512자."
        ),
    )


class ApiKeyUpdateResponse(BaseModel):
    has_api_key: bool = Field(description="등록 후 키 보유 여부 — 항상 true")


LeaderboardPeriod = Literal["all", "week"]


class LeaderboardEntry(BaseModel):
    """리더보드 한 행. period에 따라 points 의미가 달라진다."""

    rank: int = Field(description="1부터 시작하는 순위 (동점이면 user_id 오름차순)")
    user_id: int = Field(examples=[1])
    display_name: str = Field(examples=["김민석"])
    tier: str = Field(description="현재 티어")
    points: int = Field(
        description=(
            "period=all이면 누적 EXP, period=week면 이번 ISO 주차에 처음 AC로 획득한 "
            "points_awarded 합"
        ),
        examples=[1500],
    )
    avatar_url: str | None = Field(
        default=None,
        description=(
            "OAuth IdP가 제공한 프로필 이미지 URL. NULL이면 클라이언트가 GitHub "
            "identicon으로 fallback."
        ),
        examples=["https://lh3.googleusercontent.com/a/..."],
    )


class LeaderboardResponse(BaseModel):
    period: LeaderboardPeriod = Field(description="all=전체 누적, week=이번 ISO 주차")
    week: str | None = Field(
        default=None,
        description="period=week일 때만 채워짐. 집계 대상 ISO 주차 'YYYY-Www'.",
        examples=["2026-W19"],
    )
    entries: list[LeaderboardEntry] = Field(
        description="points 내림차순. 동점은 user_id 오름차순으로 안정 정렬."
    )


class TutorResponse(BaseModel):
    submission_id: int
    message: str = Field(description="튜터가 생성한 한국어 가이드 메시지")


class TutorHistoryItem(BaseModel):
    id: int = Field(description="tutor_message 행 ID")
    message: str
    created_at: datetime


class TutorHistoryResponse(BaseModel):
    submission_id: int
    messages: list[TutorHistoryItem] = Field(
        description="생성 시각 오름차순"
    )
    usage_count: int = Field(
        description="이 문제에 대한 튜터 사용 횟수 (사용자 요청만 카운트)"
    )
    remaining_uses: int = Field(
        description="남은 튜터 사용 횟수 (3회 - usage_count, 최소 0)"
    )


# ── Notices ──────────────────────────────────────────────────────────────
class Notice(BaseModel):
    id: int
    title: str
    body: str
    pinned: bool = False
    created_at: datetime
    updated_at: datetime


class NoticeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    pinned: bool = False


class NoticeUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20_000)
    pinned: bool | None = None


# ── Bug reports ──────────────────────────────────────────────────────────
BugReportCategory = Literal["judging", "statement", "sample", "system", "other"]
BugReportStatus = Literal["open", "in_progress", "resolved", "rejected"]


class BugReportCreateRequest(BaseModel):
    """사용자가 Solver 화면에서 제보. problem_id는 옵션 (시스템/UI 카테고리 대비).
    code_snapshot은 BugReportModal의 includeCode 체크박스가 켜졌을 때만 채워서 보냄."""

    category: BugReportCategory
    title: str = Field(min_length=4, max_length=200)
    body: str = Field(min_length=10, max_length=10_000)
    problem_id: int | None = None
    # MAX_CODE_LENGTH와 동일한 상한 — Solver의 코드 에디터에서 그대로 넘어옴.
    code_snapshot: str | None = Field(default=None, max_length=MAX_CODE_LENGTH)


class BugReportCreateResponse(BaseModel):
    id: int
    status: BugReportStatus = "open"


class BugReport(BaseModel):
    """관리자 목록/상세 응답. user_display_name/problem_title은 join으로 채움."""

    id: int
    user_id: int
    user_display_name: str | None = None
    problem_id: int | None = None
    problem_title: str | None = None
    category: BugReportCategory
    title: str
    body: str
    code_snapshot: str | None = None
    status: BugReportStatus
    admin_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class BugReportUpdateRequest(BaseModel):
    """관리자 상태/메모 토글. None인 필드는 미변경."""

    status: BugReportStatus | None = None
    admin_notes: str | None = Field(default=None, max_length=10_000)
