"""FastAPI 서버 — 출제 파이프라인 + 문제/스팬 조회 API.

주요 엔드포인트:
  POST /api/runs                       파이프라인 실행 시작 → {run_id, trace_id}
  GET  /api/runs/{run_id}/events       SSE: {type:'update'|'done'|'error', ...}
  GET  /api/problems                   원본 문제 리스트 (변형 통계 포함)
  GET  /api/problems/{id}              문제 상세 (intent, test_cases, authoring_meta)
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
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .config import ensure_backend_on_path

ensure_backend_on_path()

if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ["LANGSMITH_API_KEY"])
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "jcq-authoring"))


app = FastAPI(title="JCodeQuest Authoring Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 메모리 상의 run 레지스트리 ────────────────────────────────────────────
_runs: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_run_traces: dict[str, str] = {}  # run_id → langsmith trace_id
_loop: asyncio.AbstractEventLoop | None = None


# ── 모델 ─────────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    problem_id: int
    count: int = 5


class RunResponse(BaseModel):
    run_id: str
    trace_id: str


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


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/runs", response_model=RunResponse)
async def create_run(req: RunRequest) -> RunResponse:
    run_id = uuid.uuid4().hex
    trace_id = str(uuid.uuid4())  # LangSmith는 UUID 형식 요구
    _runs[run_id] = asyncio.Queue()
    _run_traces[run_id] = trace_id
    threading.Thread(
        target=_run_pipeline_blocking,
        args=(run_id, trace_id, req.problem_id, req.count),
        daemon=True,
    ).start()
    return RunResponse(run_id=run_id, trace_id=trace_id)


@app.get("/api/runs/{run_id}/events")
async def stream_events(run_id: str):
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


# ── 문제 조회 (DB) ────────────────────────────────────────────────────────
def _row_to_summary(row, child_stats: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    stats = (child_stats or {}).get(row.id, {"count": 0, "avg_judge_score": None})
    return {
        "id": row.id,
        "title": row.title,
        "category": row.category,
        "level": row.level,
        "status": row.status,
        "parent_id": row.parent_id,
        "langsmith_trace_id": row.langsmith_trace_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "child_count": stats["count"],
        "avg_judge_score": stats["avg_judge_score"],
    }


def _row_to_detail(row) -> dict[str, Any]:
    base = _row_to_summary(row)
    base.update(
        {
            "statement": row.statement,
            "reference_code": row.reference_code,
            "intent_rubric": row.intent_rubric,
            "authoring_meta": row.authoring_meta,
            "points": row.points,
            "time_limit_ms": row.time_limit_ms,
            "memory_limit_mb": row.memory_limit_mb,
            "test_cases": [
                {
                    "ordinal": t.ordinal,
                    "stdin": t.stdin,
                    "expected_stdout": t.expected_stdout,
                    "is_sample": t.is_sample,
                }
                for t in row.test_cases
            ],
        }
    )
    return base


@app.get("/api/problems")
async def list_problems(originals_only: bool = True) -> list[dict[str, Any]]:
    """원본(parent_id IS NULL) 문제 목록과 변형 통계를 반환."""
    from sqlmodel import select

    from src.storage.db import get_session  # type: ignore[import]
    from src.storage.models import ProblemRow  # type: ignore[import]

    with get_session() as session:
        stmt = select(ProblemRow)
        if originals_only:
            stmt = stmt.where(ProblemRow.parent_id.is_(None))  # type: ignore[union-attr]
        rows = list(session.exec(stmt).all())

        # 자식 통계 한 번에 집계
        all_children = list(
            session.exec(select(ProblemRow).where(ProblemRow.parent_id.is_not(None))).all()  # type: ignore[union-attr]
        )
        child_stats: dict[int, dict[str, Any]] = {}
        for row in all_children:
            pid = row.parent_id
            if pid is None:
                continue
            bucket = child_stats.setdefault(pid, {"count": 0, "scores": []})
            bucket["count"] += 1
            score = (row.authoring_meta or {}).get("judge_score")
            if isinstance(score, (int, float)):
                bucket["scores"].append(score)
        for pid, bucket in child_stats.items():
            scores = bucket.pop("scores")
            bucket["avg_judge_score"] = (sum(scores) / len(scores)) if scores else None

        return [_row_to_summary(r, child_stats) for r in rows]


@app.get("/api/problems/{problem_id}")
async def get_problem_detail(problem_id: int) -> dict[str, Any]:
    from src.storage.db import get_session  # type: ignore[import]
    from src.storage.models import ProblemRow  # type: ignore[import]

    with get_session() as session:
        row = session.get(ProblemRow, problem_id)
        if row is None:
            raise HTTPException(status_code=404, detail="problem not found")
        return _row_to_detail(row)


@app.get("/api/problems/{problem_id}/children")
async def list_problem_children(problem_id: int) -> list[dict[str, Any]]:
    from sqlmodel import select

    from src.storage.db import get_session  # type: ignore[import]
    from src.storage.models import ProblemRow  # type: ignore[import]

    with get_session() as session:
        rows = list(
            session.exec(
                select(ProblemRow).where(ProblemRow.parent_id == problem_id)  # type: ignore[arg-type]
            ).all()
        )
        return [_row_to_detail(r) for r in rows]


# ── LangSmith 스팬 ───────────────────────────────────────────────────────
@app.get("/api/spans/{trace_id}")
async def get_spans(trace_id: str) -> dict[str, Any]:
    """trace_id로 LangSmith의 모든 child run을 가져와 prompts/IO/tokens/latency를 정리."""
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
        # 비용 (있는 경우)
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
            "tokens": {
                "prompt": prompt_t,
                "completion": comp_t,
                "total": usage,
            },
            "cost": cost,
            "inputs": run.inputs,
            "outputs": run.outputs,
            "error": run.error,
            "extra": (run.extra or {}).get("metadata") if run.extra else None,
            "tags": list(run.tags or []),
        }

    serialized = [_serialize(r) for r in runs]
    serialized.sort(key=lambda r: r["start_time"] or "")

    # 토큰/시간 집계
    total_tokens = sum((s["tokens"]["total"] or 0) for s in serialized)
    total_prompt = sum((s["tokens"]["prompt"] or 0) for s in serialized)
    total_completion = sum((s["tokens"]["completion"] or 0) for s in serialized)
    total_latency = sum((s["latency_seconds"] or 0) for s in serialized if s["parent_run_id"] is None)

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
