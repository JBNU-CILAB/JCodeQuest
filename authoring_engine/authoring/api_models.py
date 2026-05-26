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
    by_user: str | None = Field(
        default=None, description="실행한 관리자 표시명 (RunsView 메타용, 옵션)"
    )

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"problem_id": 1, "count": 5}]}
    )


class RetryRequest(BaseModel):
    from_node: str | None = Field(
        default=None,
        description="실패 노드부터 재실행 힌트(현재는 전체 재실행으로 폴백).",
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


# ── /api/admin/comparison ────────────────────────────────────────────────
# compare_to_original 노드가 authoring_meta.comparison에 넣어 둔 3축 정량 기록을
# admin dashboard에서 그래프/표로 쓰기 좋은 형태로 추출·집계해 노출한다. 게이트 아님.

class ProblemComparisonOut(BaseModel):
    """단일 변형 1건의 compare_to_original 결과."""

    problem_id: int = Field(description="변형 문제 ID")
    parent_id: int | None = Field(default=None, description="원본 문제 ID")
    title: str
    level: str
    hallucination_score: float | None = Field(
        default=None,
        description="0=환각 없음, 1=환각 심함. compare_to_original 노드가 미실행이면 null.",
    )
    intent_similarity: float | None = Field(
        default=None, description="0=무관, 1=원본과 같은 알고리즘 부류."
    )
    difficulty_similarity: float | None = Field(
        default=None, description="0=난이도 차이 큼, 1=거의 동일."
    )
    rationale: str = ""
    error: str = ""
    judge_score: float | None = Field(
        default=None, description="기존 3-judge 품질 점수 (참고용)."
    )
    solver_passed: bool | None = None


class ComparisonStats(BaseModel):
    """수치 1개 컬럼에 대한 요약 통계 (대시보드 카드용)."""

    count: int = Field(description="None이 아닌 표본 수")
    mean: float | None = None
    min: float | None = None
    max: float | None = None


class ComparisonAggregateOut(BaseModel):
    """한 원본의 모든 변형에 대한 비교 점수 집계 + 개별 엔트리."""

    original_id: int
    original_title: str
    variant_count: int = Field(description="parent_id == original_id인 문제 총 수")
    scored_count: int = Field(
        description="hallucination_score가 채워진 (compare 노드가 돈) 변형 수"
    )
    hallucination: ComparisonStats
    intent_similarity: ComparisonStats
    difficulty_similarity: ComparisonStats
    variants: list[ProblemComparisonOut]


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
