"""server 라우트가 쓰는 Pydantic 모델.

`authoring/schemas.py`는 LangGraph 파이프라인 state(TypedDict) 전용이라
API 모델은 여기에 분리해 둔다.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── /api/runs ────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    problem_id: int = Field(description="변형의 부모가 될 원본 문제 ID", examples=[1])
    count: int = Field(
        default=5, ge=1, le=20,
        description="생성할 변형 개수 (검증/심사 통과 시에만 저장됨)",
    )

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"problem_id": 1, "count": 5}]}
    )


class RunResponse(BaseModel):
    run_id: str = Field(description="이 실행에 대한 메모리 큐 키 — SSE에서 사용")
    trace_id: str = Field(
        description="LangSmith 트레이스 ID (UUID). /api/spans/{trace_id}로 조회."
    )


# ── /api/problems ────────────────────────────────────────────────────────
class ProblemSummaryOut(BaseModel):
    id: int
    title: str
    category: str
    level: str
    status: str = Field(description="approved | draft | rejected ...")
    parent_id: int | None = None
    langsmith_trace_id: str | None = None
    created_at: str | None = None
    child_count: int = 0
    avg_judge_score: float | None = None


class TestCasePublicOut(BaseModel):
    ordinal: int
    stdin: str
    expected_stdout: str
    is_sample: bool


class ProblemDetailOut(ProblemSummaryOut):
    statement: str
    reference_code: str
    intent_rubric: dict[str, Any] | None = None
    authoring_meta: dict[str, Any] | None = None
    points: int
    time_limit_ms: int
    memory_limit_mb: int
    test_cases: list[TestCasePublicOut]


class TestCaseInput(BaseModel):
    stdin: str = Field(description="표준입력 (개행이 없으면 자동 부착)")
    expected_stdout: str = Field(
        default="",
        description="기대 표준출력. 비면 reference_code를 sandbox에서 실행해 자동 채움.",
    )
    is_sample: bool = Field(default=False, description="공개 샘플 여부")


class CreateOriginalRequest(BaseModel):
    """원본 문제 1건을 status='approved'로 직접 등록. 출제 엔진 우회 — 운영자/시드 용도."""

    title: str = Field(examples=["두 배 출력"])
    statement: str = Field(description="문제 본문 (Markdown 허용)")
    category: str = Field(default="basic")
    level: str = Field(
        default="bronze",
        description="bronze | silver | gold",
        pattern=r"^(bronze|silver|gold)$",
    )
    points: int = Field(default=100, ge=0, le=1000)
    time_limit_ms: int = Field(default=2000, ge=100, le=60000)
    memory_limit_mb: int = Field(default=256, ge=16, le=2048)
    reference_code: str = Field(
        description="autofill에 사용될 정답 Python 소스",
        examples=["n = int(input())\nprint(n * 2)\n"],
    )
    one_line_summary: str = ""
    expected_approach: str = ""
    key_insight: str = ""
    expected_complexity: str = ""
    must_handle: list[str] = []
    forbidden_patterns: list[str] = []
    test_cases: list[TestCaseInput] = Field(
        min_length=1, description="최소 1개. expected_stdout 비면 자동 채움."
    )


class CreateOriginalResponse(BaseModel):
    id: int = Field(description="새로 등록된 문제 ID")
    autofill: list[dict[str, Any]] = Field(
        description="자동 채움된 케이스의 메타 (ordinal/elapsed_ms/expected 일부)"
    )


# ── /api/spans ───────────────────────────────────────────────────────────
class SpanTokens(BaseModel):
    prompt: int | None = None
    completion: int | None = None
    total: int | None = None


class SpanOut(BaseModel):
    id: str
    parent_run_id: str | None = None
    name: str
    run_type: str
    status: str
    start_time: str | None = None
    end_time: str | None = None
    latency_seconds: float | None = None
    tokens: SpanTokens
    cost: float | None = None
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    error: str | None = None
    extra: dict[str, Any] | None = None
    tags: list[str] = []


class SpansSummary(BaseModel):
    span_count: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    root_latency_seconds: float


class SpansResponse(BaseModel):
    trace_id: str
    project: str
    summary: SpansSummary
    spans: list[SpanOut]
