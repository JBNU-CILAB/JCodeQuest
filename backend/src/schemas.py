from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from jcq_shared.schemas import IntentRubric, Problem, ProblemLevel, TestCase

__all__ = ["IntentRubric", "Problem", "ProblemLevel", "TestCase"]

Verdict = Literal["AC", "SUS"]
EnsembleVerdict = Literal["AC", "SUS"]
EnsembleMode = Literal["unanimous", "majority"]
ExecStatus = Literal["OK", "TLE", "MLE", "RE"]


class ExecResult(BaseModel):
    status: ExecStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    elapsed_ms: int = 0
    peak_memory_kb: int = 0


class TestResult(BaseModel):
    ordinal: int
    passed: bool
    status: ExecStatus = "OK"
    actual_stdout: str | None = None
    error: str | None = None
    elapsed_ms: int = 0
    peak_memory_kb: int = 0


class Submission(BaseModel):
    id: int
    user_id: int
    problem_id: int
    code: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class JudgeVotePartial(BaseModel):
    """LLM이 직접 채우는 필드만 담는 스키마. judge_id는 호출자가 주입."""

    verdict: Verdict
    intent_match: bool
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class JudgeVote(JudgeVotePartial):
    judge_id: str # 어떤 모델이 채점했는지 자신의 ID Sign (Melchior, Balthasar, Casper)


class EnsembleResult(BaseModel):
    final_verdict: EnsembleVerdict
    mode: EnsembleMode
    votes: list[JudgeVote]


JobStatus = Literal["queued", "running", "done", "failed"]

# 제출 코드 길이 상한 — 알고리즘 풀이는 통상 수 KB. 페이로드 폭주로 DB·메모리를 흔드는
# 케이스 차단. 변경 시 storage.submissions.MAX_ATTEMPTS와 무관.
MAX_CODE_LENGTH = 64 * 1024


class GradeRequest(BaseModel):
    """user_id는 인증된 세션에서 추출 — body로 받지 않음(위조 차단)."""

    problem_id: int
    code: str = Field(min_length=1, max_length=MAX_CODE_LENGTH)


class GradeAcceptedResponse(BaseModel):
    submission_id: int
    status: JobStatus = "queued"


class SubmissionStatusResponse(BaseModel):
    submission_id: int
    status: JobStatus
    final_verdict: EnsembleVerdict | None = None
    test_results: list[TestResult] | None = None
    ensemble: EnsembleResult | None = None
    points_awarded: int | None = None


class PublicTestCase(BaseModel):
    """학생에게 노출되는 샘플 케이스. hidden 케이스의 stdin/expected는 절대 포함하지 않음."""

    ordinal: int
    stdin: str
    expected_stdout: str


class ProblemSummary(BaseModel):
    """목록용 — reference_code / intent_rubric 내부는 제외."""

    id: int
    title: str
    category: str
    level: Literal["bronze", "silver", "gold"]
    points: int
    one_line_summary: str


class ProblemDetail(BaseModel):
    """상세 — statement와 샘플 케이스만 공개. 채점 기준/정답 코드는 비공개."""

    id: int
    title: str
    statement: str
    category: str
    level: Literal["bronze", "silver", "gold"]
    points: int
    time_limit_ms: int
    memory_limit_mb: int
    one_line_summary: str
    sample_test_cases: list[PublicTestCase] = Field(default_factory=list)


class AttemptStatusResponse(BaseModel):
    """제출 화면이 '남은 시도 횟수 / 쿨다운 / AC 여부'를 한 번에 보고 그릴 수 있도록 묶음."""

    problem_id: int
    attempts: int
    remaining: int
    max_attempts: int
    solved: bool
    cooldown_remaining_s: float
    can_submit: bool


class SubmissionListItem(BaseModel):
    """본인 제출 목록용 — code는 페이로드 비대해서 제외. 상세는 /grade/{id}로."""

    id: int
    problem_id: int
    status: JobStatus
    final_verdict: EnsembleVerdict | None = None
    mode: EnsembleMode | None = None
    points_awarded: int | None = None
    max_elapsed_ms: int | None = None
    peak_memory_kb: int | None = None
    created_at: datetime


class SubmissionListResponse(BaseModel):
    items: list[SubmissionListItem]
    total: int
    limit: int
    offset: int


class TutorResponse(BaseModel):
    submission_id: int
    message: str


class TutorHistoryItem(BaseModel):
    id: int
    message: str
    created_at: datetime


class TutorHistoryResponse(BaseModel):
    submission_id: int
    messages: list[TutorHistoryItem]
