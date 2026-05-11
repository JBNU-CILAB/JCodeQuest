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
