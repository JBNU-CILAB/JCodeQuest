"""파이프라인 실행 라우터 + 인메모리 run 레지스트리.

레지스트리는 모듈 전역 — 단일 프로세스 한정. 멀티 워커로 갈 때는 외부 스토리지 필요.
SSE 엔드포인트도 admin 의존성에 포함 — 브라우저에서 직접 구독할 거면
EventSource는 헤더를 못 보내니 query token이나 폴리필이 필요하다.
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from sse_starlette.sse import EventSourceResponse

from ..admin_auth import require_admin
from ..api_models import RunRequest, RunResponse

router = APIRouter(tags=["runs"], dependencies=[Depends(require_admin)])


# ── 인메모리 레지스트리 ───────────────────────────────────────────────────
_runs: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_run_traces: dict[str, str] = {}
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """server.py startup에서 호출 — 워커 스레드가 큐에 push할 때 사용한다."""
    global _loop  # noqa: PLW0603
    _loop = loop


def _push(run_id: str, payload: dict[str, Any]) -> None:
    q = _runs.get(run_id)
    if q is None or _loop is None:
        return
    asyncio.run_coroutine_threadsafe(q.put(payload), _loop)


def _run_pipeline_blocking(run_id: str, trace_id: str, problem_id: int, count: int) -> None:
    try:
        from langchain_core.runnables import RunnableConfig

        from ..pipeline.graph import build_graph

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


@router.post(
    "/api/runs",
    response_model=RunResponse,
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


@router.get(
    "/api/runs/{run_id}/events",
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
