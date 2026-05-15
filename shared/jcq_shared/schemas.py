from typing import Literal

from pydantic import BaseModel, Field

ProblemLevel = Literal["bronze", "silver", "gold"]


class IntentRubric(BaseModel):
    expected_approach: str
    expected_complexity: str
    must_handle: list[str] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)
    key_insight: str
    one_line_summary: str


class TestCase(BaseModel):
    ordinal: int
    stdin: str
    expected_stdout: str
    is_sample: bool = False


class Problem(BaseModel):
    id: int
    title: str
    statement: str
    category: str
    level: ProblemLevel = "bronze"
    points: int = 100
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256
    reference_code: str
    intent_rubric: IntentRubric
    test_cases: list[TestCase] = Field(default_factory=list)


# ── 채점 도메인 타입 ────────────────────────────────────────────────────────
# backend와 judge_engine이 HTTP로 주고받는 페이로드라 한쪽에만 두면 wire drift가 생긴다.
Verdict = Literal["AC", "SUS"]
EnsembleVerdict = Literal["AC", "SUS"]
EnsembleMode = Literal["unanimous", "majority"]
ExecStatus = Literal["OK", "TLE", "MLE", "RE"]


class ExecResult(BaseModel):
    status: ExecStatus = Field(
        description="실행 종료 분류 — OK(정상), TLE(시간초과), MLE(메모리초과), RE(런타임에러)",
    )
    stdout: str = Field(default="", description="표준출력 (최대 64 KiB)")
    stderr: str = Field(default="", description="표준에러 (최대 64 KiB)")
    exit_code: int | None = Field(
        default=None, description="프로세스 종료 코드. 비정상 종료 시 None일 수 있음."
    )
    elapsed_ms: int = Field(default=0, description="실행 소요 시간 (ms)")
    peak_memory_kb: int = Field(default=0, description="피크 메모리 사용량 (KB)")


class TestResult(BaseModel):
    ordinal: int = Field(description="테스트 케이스 순번 (1부터)", examples=[1])
    passed: bool = Field(description="해당 케이스 통과 여부", examples=[True])
    status: ExecStatus = Field(
        default="OK", description="실행 분류 — passed=False일 때만 OK 외 값 가능"
    )
    actual_stdout: str | None = Field(
        default=None, description="실제 표준출력 (스니펫). 실패 시 비교용으로 노출."
    )
    error: str | None = Field(
        default=None, description="RE 등 비정상 종료 시 stderr 요약"
    )
    elapsed_ms: int = Field(default=0, description="이 케이스 실행 시간 (ms)")
    peak_memory_kb: int = Field(default=0, description="이 케이스 피크 메모리 (KB)")


class JudgeVotePartial(BaseModel):
    """LLM이 직접 채우는 필드만 담는 스키마. judge_id는 호출자가 주입."""

    verdict: Verdict = Field(
        description="이 심판의 판정 — AC(합격) 또는 SUS(의심)"
    )
    intent_match: bool = Field(
        description="제출 코드가 출제 의도(rubric)와 일치한다고 보는지"
    )
    rationale: str = Field(description="판정 근거 (자연어)")
    confidence: float = Field(ge=0.0, le=1.0, description="0.0–1.0 신뢰도")


class JudgeVote(JudgeVotePartial):
    judge_id: str = Field(
        description="모델 식별자 (Melchior | Balthasar | Casper)",
        examples=["Melchior"],
    )


class EnsembleResult(BaseModel):
    final_verdict: EnsembleVerdict = Field(
        description="3명의 심판 투표를 종합한 최종 판정"
    )
    mode: EnsembleMode = Field(
        description="unanimous=3/3 동일, majority=2/3 다수결"
    )
    votes: list[JudgeVote] = Field(description="개별 심판의 판정 목록 (3개)")


# ── judge_engine ↔ backend HTTP 페이로드 ───────────────────────────────────
# 흐름:
#   1) backend → judge_engine  POST /api/grade  (GradeSubmitRequest)        → 202
#   2) judge_engine 워커가 큐에서 꺼냄 → backend로 webhook  (GradeEvent running)
#   3) 채점 완료/실패 → backend로 webhook  (GradeEvent done | failed)
#
# 모든 webhook은 `Authorization: Bearer <JCQ_INTERNAL_SECRET>` 헤더로 인증한다.

GradeEventType = Literal["running", "done", "failed"]


class GradeSubmitRequest(BaseModel):
    """backend → judge_engine. 채점 작업 큐잉 요청."""

    submission_id: int = Field(description="backend의 SubmissionRow.id — webhook의 식별자")
    problem: Problem
    code: str


class GradeEvent(BaseModel):
    """judge_engine → backend. 채점 라이프사이클 이벤트.

    event=running: 다른 필드 모두 None. 시작 알림.
    event=done:    test_results/all_passed/ensemble 채워짐. 최종 결과.
    event=failed:  error에 사유. test_results 등은 부분 채움 가능.
    """

    submission_id: int
    event: GradeEventType
    test_results: list[TestResult] | None = None
    all_passed: bool | None = None
    ensemble: EnsembleResult | None = None
    error: str | None = None


# ── authoring_engine ↔ backend HTTP 페이로드 ───────────────────────────────
# 출제 엔진은 backend의 /internal/* 라우트로 문제를 조회·저장한다 (Bearer 인증 동일).
# 코드 실행이 필요한 경우 judge_engine의 /api/sandbox/run을 호출 — backend는 DB·전송만.

ProblemStatus = Literal["draft", "approved", "rejected"]


class AuthoringProblemCreate(BaseModel):
    """authoring_engine → backend. 변형 또는 시드 문제 생성 요청."""

    problem: Problem = Field(description="신규 문제 (id 필드는 무시됨)")
    status: ProblemStatus = Field(default="approved")
    parent_id: int | None = Field(
        default=None, description="원본 문제 ID. 시드/수동 등록 시 None."
    )
    langsmith_trace_id: str | None = Field(
        default=None, description="LangSmith 트레이스 UUID — 출제 파이프라인 추적용."
    )
    authoring_meta: dict | None = Field(
        default=None,
        description="judge_score, solver_results 등 출제 파이프라인의 부산물.",
    )
    iso_week: str | None = Field(
        default=None,
        description="'YYYY-Www' 라벨. 비우면 backend가 현재 UTC 주차로 채움.",
    )


class AuthoringProblemCreateResponse(BaseModel):
    id: int = Field(description="새로 저장된 ProblemRow.id")


class AuthoringTestCase(BaseModel):
    ordinal: int
    stdin: str
    expected_stdout: str
    is_sample: bool


class AuthoringProblemAdmin(BaseModel):
    """backend → authoring_engine. 관리자 시야의 문제 상세 (히든 필드까지 노출)."""

    id: int
    title: str
    statement: str
    category: str
    level: ProblemLevel
    points: int
    time_limit_ms: int
    memory_limit_mb: int
    reference_code: str
    intent_rubric: IntentRubric
    test_cases: list[AuthoringTestCase]
    status: str
    parent_id: int | None = None
    langsmith_trace_id: str | None = None
    authoring_meta: dict | None = None
    iso_week: str | None = None
    created_at: str | None = None


class AuthoringProblemSummary(BaseModel):
    """원본 목록용 — 변형 통계 포함."""

    id: int
    title: str
    category: str
    level: ProblemLevel
    status: str
    parent_id: int | None = None
    langsmith_trace_id: str | None = None
    created_at: str | None = None
    child_count: int = 0
    avg_judge_score: float | None = None


class SandboxRunRequest(BaseModel):
    """authoring_engine → judge_engine. 일회성 동기 sandbox 실행."""

    code: str
    stdin: str = ""
    time_limit_ms: int = Field(default=2000, ge=100, le=60000)
    memory_limit_mb: int = Field(default=256, ge=16, le=2048)


# ── admin 대시보드 ─────────────────────────────────────────────────────
class ProblemDeleteCascade(BaseModel):
    """delete_problem이 돌려주는 cascade 카운트 — 사용자에게 "X건 함께 삭제됨" 표시용."""

    variants: int = 0
    submissions: int = 0
    tutor_messages: int = 0
    test_cases: int = 0


class ProblemDeleteResponse(BaseModel):
    id: int
    cascade: ProblemDeleteCascade


class AdminSubmissionSummary(BaseModel):
    """submission 목록 — 코드/테스트결과/votes 같은 무거운 필드 제외."""

    id: int
    user_id: int
    user_display_name: str | None = None
    problem_id: int
    problem_title: str | None = None
    status: str
    final_verdict: str | None = None
    mode: str | None = None
    max_elapsed_ms: int | None = None
    peak_memory_kb: int | None = None
    points_awarded: int | None = None
    created_at: str | None = None


class AdminSubmissionDetail(AdminSubmissionSummary):
    """submission 상세 — 무거운 필드 포함."""

    code: str
    votes: list | None = None
    test_results: list | None = None
