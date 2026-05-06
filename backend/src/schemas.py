from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["AC", "WA", "SUS"]
EnsembleVerdict = Literal["AC", "SUS"]
EnsembleMode = Literal["unanimous", "majority", "split"]


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


class TestResult(BaseModel):
    ordinal: int
    passed: bool
    actual_stdout: str | None = None
    error: str | None = None


class Problem(BaseModel):
    id: int
    title: str
    statement: str
    category: str
    level: Literal["bronze", "silver", "gold"] = "bronze"
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


class JudgeVote(BaseModel):
    judge_id: str
    verdict: Verdict
    intent_match: bool
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


class EnsembleResult(BaseModel):
    final_verdict: EnsembleVerdict
    mode: EnsembleMode
    votes: list[JudgeVote]


class GradeRequest(BaseModel):
    user_id: int
    problem_id: int
    code: str
    test_results: list[TestResult] = Field(default_factory=list)


class GradeResponse(BaseModel):
    submission_id: int
    ensemble: EnsembleResult
