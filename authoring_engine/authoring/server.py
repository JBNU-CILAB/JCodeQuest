"""FastAPI 서버 — 출제 파이프라인 + 문제/스팬 조회 API.

DB는 backend가 단일 소유 — 이 서버는 `/internal/*` 라우트로 backend에 위임한다.
sandbox 실행도 마찬가지로 judge_engine의 `/api/sandbox/run`을 호출.

주요 엔드포인트:
  POST /api/runs                       파이프라인 실행 시작 → {run_id, trace_id}
  GET  /api/runs/{run_id}/events       SSE: {type:'update'|'done'|'error', ...}
  GET  /api/problems                   원본 문제 리스트 (변형 통계 포함)
  GET  /api/problems/{id}              문제 상세 (intent, test_cases, authoring_meta)
  POST /api/problems                   시드/원본 문제 직접 등록
  GET  /api/problems/{id}/children     해당 원본의 변형 목록
  GET  /api/spans/{trace_id}           LangSmith 스팬 트리 (prompts/IO/tokens/latency)
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import httpx
from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.middleware.cors import CORSMiddleware
from jcq_shared.schemas import IntentRubric, Problem, TestCase
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse

from . import backend_client

if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ["LANGSMITH_API_KEY"])
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "jcq-authoring"))


tags_metadata = [
    {"name": "health", "description": "liveness probe"},
    {"name": "runs", "description": "출제 파이프라인 실행 + SSE 진행 스트림"},
    {"name": "problems", "description": "원본/변형 문제 조회와 원본 직접 등록"},
    {"name": "spans", "description": "LangSmith 트레이스 조회"},
]

app = FastAPI(
    title="JCodeQuest Authoring Engine",
    description=(
        "LangGraph 파이프라인으로 원본 문제로부터 변형을 생성하는 출제 엔진. "
        "DB·sandbox는 backend·judge_engine에 위임 — 내부 HTTP API로 통신."
    ),
    version="0.2.0",
    openapi_tags=tags_metadata,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500", "http://127.0.0.1:5500",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 메모리 상의 run 레지스트리 ────────────────────────────────────────────
_runs: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_run_traces: dict[str, str] = {}  # run_id → langsmith trace_id
_loop: asyncio.AbstractEventLoop | None = None


# ── 모델 ─────────────────────────────────────────────────────────────────
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


# ── 파이프라인 실행 ──────────────────────────────────────────────────────
def _push(run_id: str, payload: dict[str, Any]) -> None:
    q = _runs.get(run_id)
    if q is None or _loop is None:
        return
    asyncio.run_coroutine_threadsafe(q.put(payload), _loop)


def _run_pipeline_blocking(run_id: str, trace_id: str, problem_id: int, count: int) -> None:
    try:
        from langchain_core.runnables import RunnableConfig

        from .pipeline.graph import build_graph

        graph = build_graph()
        initial_state = {
            "original_problem_id": problem_id,
            "target_count": count,
            "original_problem": None,
            "seeds": [],
            "candidates": [],
            "saved_problem_ids": [],
            "errors": [],
            "langsmith_trace_id": trace_id,
        }
        config = RunnableConfig(
            run_id=uuid.UUID(trace_id),
            run_name="authoring_pipeline",
            tags=["authoring", f"problem_{problem_id}"],
        )

        for chunk in graph.stream(initial_state, config=config):
            _push(run_id, {"type": "update", "data": chunk})

        _push(run_id, {"type": "done", "trace_id": trace_id})
    except Exception as e:  # pylint: disable=broad-except
        _push(run_id, {"type": "error", "message": f"{type(e).__name__}: {e}"})


@app.on_event("startup")
async def _capture_loop() -> None:
    global _loop  # noqa: PLW0603
    _loop = asyncio.get_running_loop()


@app.get(
    "/api/health",
    tags=["health"],
    summary="Liveness probe",
)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/runs",
    response_model=RunResponse,
    tags=["runs"],
    summary="출제 파이프라인 실행 시작",
)
async def create_run(req: RunRequest) -> RunResponse:
    run_id = uuid.uuid4().hex
    trace_id = str(uuid.uuid4())
    _runs[run_id] = asyncio.Queue()
    _run_traces[run_id] = trace_id
    threading.Thread(
        target=_run_pipeline_blocking,
        args=(run_id, trace_id, req.problem_id, req.count),
        daemon=True,
    ).start()
    return RunResponse(run_id=run_id, trace_id=trace_id)


@app.get(
    "/api/runs/{run_id}/events",
    tags=["runs"],
    summary="파이프라인 진행 SSE 스트림",
)
async def stream_events(
    run_id: Annotated[str, PathParam(description="POST /api/runs가 반환한 run_id")]
):
    q = _runs.get(run_id)
    if q is None:
        raise HTTPException(status_code=404, detail="run not found")

    async def generator():
        try:
            while True:
                payload = await q.get()
                yield {"data": json.dumps(payload, ensure_ascii=False, default=str)}
                if payload.get("type") in ("done", "error"):
                    return
        finally:
            _runs.pop(run_id, None)

    return EventSourceResponse(generator())


# ── 문제 조회 (backend로 위임) ─────────────────────────────────────────────
def _admin_to_summary(admin: dict[str, Any]) -> dict[str, Any]:
    """backend AuthoringProblemSummary/Admin 응답을 viewer 응답 모델로 매핑."""
    return {
        "id": admin["id"],
        "title": admin["title"],
        "category": admin["category"],
        "level": admin["level"],
        "status": admin["status"],
        "parent_id": admin.get("parent_id"),
        "langsmith_trace_id": admin.get("langsmith_trace_id"),
        "created_at": admin.get("created_at"),
        "child_count": admin.get("child_count", 0),
        "avg_judge_score": admin.get("avg_judge_score"),
    }


def _admin_to_detail(admin: dict[str, Any]) -> dict[str, Any]:
    base = _admin_to_summary(admin)
    base.update(
        {
            "statement": admin["statement"],
            "reference_code": admin["reference_code"],
            "intent_rubric": admin.get("intent_rubric"),
            "authoring_meta": admin.get("authoring_meta"),
            "points": admin["points"],
            "time_limit_ms": admin["time_limit_ms"],
            "memory_limit_mb": admin["memory_limit_mb"],
            "test_cases": admin.get("test_cases", []),
        }
    )
    return base


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    """backend가 돌려준 4xx/5xx를 그대로 transport — 메시지에 원본 status 포함."""
    return HTTPException(
        status_code=e.response.status_code,
        detail=f"backend: {e.response.text[:200]}",
    )


@app.get(
    "/api/problems",
    response_model=list[ProblemSummaryOut],
    tags=["problems"],
    summary="문제 목록 (변형 통계 포함)",
)
async def list_problems(
    originals_only: Annotated[
        bool, Query(description="false면 변형까지 모두 포함")
    ] = True,
) -> list[dict[str, Any]]:
    try:
        rows = backend_client.list_problems(originals_only=originals_only)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    return [_admin_to_summary(r.model_dump()) for r in rows]


@app.get(
    "/api/problems/{problem_id}",
    response_model=ProblemDetailOut,
    tags=["problems"],
    summary="문제 상세 (관리자 시야)",
    responses={404: {"description": "문제 없음"}},
)
async def get_problem_detail(
    problem_id: Annotated[int, PathParam(description="문제 ID")]
) -> dict[str, Any]:
    try:
        admin = backend_client.fetch_problem(problem_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    return _admin_to_detail(admin.model_dump())


@app.post(
    "/api/problems",
    response_model=CreateOriginalResponse,
    tags=["problems"],
    summary="원본 문제 직접 등록 (출제 엔진 우회)",
    description=(
        "운영자/시드 용도. `expected_stdout`이 비어 있으면 judge_engine 샌드박스에서 "
        "reference_code를 실행해 자동으로 채운다. 그 후 backend에 POST해 저장한다."
    ),
    responses={
        400: {"description": "test_cases 비었거나 level 부정"},
        422: {"description": "autofill 실패 — case <i>: <status>"},
    },
)
async def create_original(req: CreateOriginalRequest) -> dict[str, Any]:
    if not req.test_cases:
        raise HTTPException(400, "test_cases 최소 1개 필요")
    if req.level not in ("bronze", "silver", "gold"):
        raise HTTPException(400, "level은 bronze|silver|gold")

    filled: list[TestCase] = []
    autofill_log: list[dict[str, Any]] = []
    for i, tc in enumerate(req.test_cases, start=1):
        stdin = tc.stdin if tc.stdin.endswith("\n") or not tc.stdin else tc.stdin + "\n"
        expected = tc.expected_stdout
        if not expected:
            r = backend_client.sandbox_run(
                req.reference_code,
                stdin,
                time_limit_ms=req.time_limit_ms,
                memory_limit_mb=req.memory_limit_mb,
            )
            if r.status != "OK":
                raise HTTPException(
                    422,
                    f"autofill 실패 — case {i}: {r.status} stderr={r.stderr[:200]!r}",
                )
            expected = r.stdout.rstrip()
            autofill_log.append(
                {"ordinal": i, "elapsed_ms": r.elapsed_ms, "expected": expected[:80]}
            )
        filled.append(
            TestCase(ordinal=i, stdin=stdin, expected_stdout=expected, is_sample=tc.is_sample)
        )

    rubric = IntentRubric(
        expected_approach=req.expected_approach or req.one_line_summary or req.title,
        expected_complexity=req.expected_complexity or "O(1)",
        must_handle=req.must_handle,
        forbidden_patterns=req.forbidden_patterns,
        key_insight=req.key_insight or req.one_line_summary or req.title,
        one_line_summary=req.one_line_summary or req.title,
    )

    problem = Problem(
        id=0,
        title=req.title,
        statement=req.statement,
        category=req.category,
        level=req.level,  # type: ignore[arg-type]
        points=req.points,
        time_limit_ms=req.time_limit_ms,
        memory_limit_mb=req.memory_limit_mb,
        reference_code=req.reference_code,
        intent_rubric=rubric,
        test_cases=filled,
    )

    meta: dict[str, Any] = {"source": "manual"}
    if autofill_log:
        meta["autofill"] = autofill_log

    try:
        pid = backend_client.create_problem(
            problem,
            status="approved",
            parent_id=None,
            authoring_meta=meta,
        )
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)

    return {"id": pid, "autofill": autofill_log}


@app.get(
    "/api/problems/{problem_id}/children",
    response_model=list[ProblemDetailOut],
    tags=["problems"],
    summary="원본의 변형 목록 (상세)",
)
async def list_problem_children(
    problem_id: Annotated[int, PathParam(description="원본 문제 ID")]
) -> list[dict[str, Any]]:
    try:
        rows = backend_client.list_children(problem_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    return [_admin_to_detail(r.model_dump()) for r in rows]


# ── LangSmith 스팬 ───────────────────────────────────────────────────────
@app.get(
    "/api/spans/{trace_id}",
    response_model=SpansResponse,
    tags=["spans"],
    summary="LangSmith 트레이스 스팬 트리",
    responses={
        404: {"description": "해당 trace_id의 run이 LangSmith에 없음"},
        500: {"description": "langsmith 클라이언트 import 실패"},
        502: {"description": "LangSmith API 호출 실패"},
        503: {"description": "LANGSMITH_API_KEY 미설정"},
    },
)
async def get_spans(
    trace_id: Annotated[str, PathParam(description="LangSmith 트레이스 UUID")]
) -> dict[str, Any]:
    if not os.getenv("LANGSMITH_API_KEY"):
        raise HTTPException(status_code=503, detail="LANGSMITH_API_KEY not configured")
    try:
        from langsmith import Client
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"langsmith client unavailable: {e}")

    client = Client()
    project = os.getenv("LANGSMITH_PROJECT", "jcq-authoring")
    try:
        runs = list(client.list_runs(project_name=project, trace_id=trace_id))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"langsmith fetch failed: {e}")

    if not runs:
        raise HTTPException(status_code=404, detail="trace not found")

    def _serialize(run) -> dict[str, Any]:
        latency = None
        if run.start_time and run.end_time:
            latency = (run.end_time - run.start_time).total_seconds()
        usage = getattr(run, "total_tokens", None)
        prompt_t = getattr(run, "prompt_tokens", None)
        comp_t = getattr(run, "completion_tokens", None)
        cost = getattr(run, "total_cost", None)
        return {
            "id": str(run.id),
            "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
            "name": run.name,
            "run_type": run.run_type,
            "status": run.status,
            "start_time": run.start_time.isoformat() if run.start_time else None,
            "end_time": run.end_time.isoformat() if run.end_time else None,
            "latency_seconds": latency,
            "tokens": {"prompt": prompt_t, "completion": comp_t, "total": usage},
            "cost": cost,
            "inputs": run.inputs,
            "outputs": run.outputs,
            "error": run.error,
            "extra": (run.extra or {}).get("metadata") if run.extra else None,
            "tags": list(run.tags or []),
        }

    serialized = [_serialize(r) for r in runs]
    serialized.sort(key=lambda r: r["start_time"] or "")

    total_tokens = sum((s["tokens"]["total"] or 0) for s in serialized)
    total_prompt = sum((s["tokens"]["prompt"] or 0) for s in serialized)
    total_completion = sum((s["tokens"]["completion"] or 0) for s in serialized)
    total_latency = sum(
        (s["latency_seconds"] or 0)
        for s in serialized
        if s["parent_run_id"] is None
    )

    return {
        "trace_id": trace_id,
        "project": project,
        "summary": {
            "span_count": len(serialized),
            "total_tokens": total_tokens,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "root_latency_seconds": total_latency,
        },
        "spans": serialized,
    }
