from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["AC", "SUS"]
EnsembleVerdict = Literal["AC", "SUS"]
EnsembleMode = Literal["unanimous", "majority"]
ExecStatus = Literal["OK", "TLE", "MLE", "RE"]


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


class Problem(BaseModel):
    id: int
    title: str
    statement: str
    category: str
    level: Literal["bronze", "silver", "gold"] = "bronze"
    points: int = 100
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256
    reference_code: str
    intent_rubric: IntentRubric
    test_cases: list[TestCase] = Field(default_factory=list)


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
    judge_id: str


class EnsembleResult(BaseModel):
    final_verdict: EnsembleVerdict
    mode: EnsembleMode
    votes: list[JudgeVote]


JobStatus = Literal["queued", "running", "done", "failed"]


class GradeRequest(BaseModel):
    user_id: int
    problem_id: int
    code: str


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
