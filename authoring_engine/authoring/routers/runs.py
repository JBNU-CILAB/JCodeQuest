"""파이프라인 실행 라우터 + 인메모리 run 레지스트리 + 영속화.

레지스트리(_runs)는 모듈 전역 — 단일 프로세스 한정, 살아있는 run의 SSE 큐만 보관한다.
**과거 run 목록·노드 상태**는 backend `/internal/runs`에 영속화한 것을 조회한다
(routers는 backend_client로 위임 — DB 단일 소유 원칙). run 시작 시 RunRow 생성 →
노드 완료마다 node_states 갱신 → 종료 시 finalize. forensics RunsView의 데이터원.

SSE 엔드포인트도 admin 의존성에 포함 — 브라우저 EventSource는 헤더를 못 보내니
query token이나 fetch-stream 폴리필이 필요하다(현 대시보드는 fetch+ReadableStream 사용).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from jcq_shared.schemas import RunCreate, RunDetail, RunSummary, RunUpdate
from sse_starlette.sse import EventSourceResponse

from .. import backend_client
from ..admin_auth import require_admin
from ..api_models import RetryRequest, RunBulkDeleteRequest, RunRequest, RunResponse
from ..langsmith_tokens import node_token_usage
from ..pipeline.node_stats import NODE_KIND, NODE_ORDER, summarize_node

log = logging.getLogger(__name__)

router = APIRouter(tags=["runs"], dependencies=[Depends(require_admin)])


# ── 인메모리 레지스트리 (라이브 SSE 큐만) ────────────────────────────────────
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


def _persist_update(run_id: str, **kw: Any) -> None:
    """backend에 run 갱신 — 실패해도 파이프라인을 막지 않는다(best-effort)."""
    try:
        backend_client.update_run(run_id, RunUpdate(**kw))
    except Exception as exc:  # noqa: BLE001
        log.warning("run %s 갱신 실패(무시): %s", run_id, exc)


def _initial_node_states() -> dict[str, dict[str, Any]]:
    return {
        k: {"status": "queued", "duration_ms": None, "retries": 0, "tokens": {}, "candidate_results": []}
        for k in NODE_ORDER
    }


def _next_queued(node_states: dict[str, dict], after: str) -> str | None:
    """after 다음 순서의 아직 queued인 노드 — 라이브 진행 표시용."""
    seen = False
    for n in NODE_ORDER:
        if n == after:
            seen = True
            continue
        if seen and node_states.get(n, {}).get("status") == "queued":
            return n
    return None


def _run_pipeline_blocking(run_id: str, trace_id: str, problem_id: int, count: int) -> None:
    from langchain_core.runnables import RunnableConfig

    from ..pipeline.graph import build_graph

    node_states = _initial_node_states()
    t_run0 = time.monotonic()
    last_ts = t_run0
    completed: list[str] = []
    errors_acc: list[str] = []
    saved_ids: list[int] = []

    # 첫 노드는 곧 실행되므로 running으로 표시 + push
    node_states[NODE_ORDER[0]]["status"] = "running"
    _push(run_id, {"type": "node", "node": NODE_ORDER[0], "state": node_states[NODE_ORDER[0]]})

    try:
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
            now = time.monotonic()
            dur = int((now - last_ts) * 1000)
            for node_key, delta in chunk.items():
                summary = summarize_node(node_key, delta if isinstance(delta, dict) else {})
                ns = node_states.get(node_key, {})
                ns.update(summary)
                ns["status"] = "done"
                ns["duration_ms"] = dur
                node_states[node_key] = ns
                completed.append(node_key)

                if node_key == "persist_approved" and isinstance(delta, dict):
                    saved_ids = list(delta.get("saved_problem_ids") or [])
                if isinstance(delta, dict) and delta.get("errors"):
                    errors_acc = list(delta["errors"])

                _push(run_id, {"type": "node", "node": node_key, "state": ns})

                # 다음 노드를 running으로 — 라이브 진행 표시
                nxt = _next_queued(node_states, node_key)
                if nxt:
                    node_states[nxt]["status"] = "running"
                    _push(run_id, {"type": "node", "node": nxt, "state": node_states[nxt]})

            last_ts = now
            _persist_update(
                run_id,
                node_states=node_states,
                saved_problem_ids=saved_ids,
                errors=errors_acc,
            )

        total_ms = int((time.monotonic() - t_run0) * 1000)
        _persist_update(
            run_id,
            status="done",
            total_duration_ms=total_ms,
            ended_at=datetime.now(timezone.utc).isoformat(),
            node_states=node_states,
            saved_problem_ids=saved_ids,
            errors=errors_acc,
        )
        _push(run_id, {"type": "done", "trace_id": trace_id, "saved_problem_ids": saved_ids})

    except Exception as exc:  # noqa: BLE001 — 한 노드가 예외를 던지면 그 지점이 실패 노드
        msg = f"{type(exc).__name__}: {exc}"
        # 완료되지 않은 첫 노드를 실패 지점으로 추정
        failed_node = next((n for n in NODE_ORDER if n not in completed), None)
        if failed_node:
            node_states[failed_node]["status"] = "failed"
            node_states[failed_node]["error"] = msg
            node_states[failed_node]["duration_ms"] = int((time.monotonic() - last_ts) * 1000)
            # 이후 노드는 skipped
            reached = False
            for n in NODE_ORDER:
                if n == failed_node:
                    reached = True
                    continue
                if reached and node_states[n]["status"] == "queued":
                    node_states[n]["status"] = "skipped"
        errors_acc = errors_acc + [msg]
        total_ms = int((time.monotonic() - t_run0) * 1000)
        _persist_update(
            run_id,
            status="failed",
            failed_at_node=failed_node,
            total_duration_ms=total_ms,
            ended_at=datetime.now(timezone.utc).isoformat(),
            node_states=node_states,
            errors=errors_acc,
        )
        _push(run_id, {"type": "error", "message": msg, "failed_at_node": failed_node})


def _start_run(problem_id: int, count: int, by_user: str | None) -> RunResponse:
    """RunRow 영속화 + 워커 스레드 기동. create_run / retry가 공유."""
    run_id = uuid.uuid4().hex
    trace_id = str(uuid.uuid4())
    _runs[run_id] = asyncio.Queue()
    _run_traces[run_id] = trace_id

    # 목록 표시용 문제 제목 — best-effort.
    problem_title: str | None = None
    try:
        problem_title = backend_client.fetch_problem(problem_id).title
    except Exception as exc:  # noqa: BLE001
        log.warning("run 시작: 문제 %s 제목 조회 실패(무시): %s", problem_id, exc)

    try:
        backend_client.create_run(
            RunCreate(
                id=run_id,
                trace_id=trace_id,
                problem_id=problem_id,
                problem_title=problem_title,
                target_count=count,
                by_user=by_user,
            )
        )
    except Exception as exc:  # noqa: BLE001 — 영속화 실패해도 라이브 run은 진행
        log.warning("run %s 영속화 실패(무시): %s", run_id, exc)

    threading.Thread(
        target=_run_pipeline_blocking,
        args=(run_id, trace_id, problem_id, count),
        daemon=True,
    ).start()
    return RunResponse(run_id=run_id, trace_id=trace_id)


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(status_code=e.response.status_code, detail=f"backend: {e.response.text[:200]}")


@router.post("/api/runs", response_model=RunResponse, summary="출제 파이프라인 실행 시작")
async def create_run(req: RunRequest) -> RunResponse:
    return _start_run(req.problem_id, req.count, req.by_user)


@router.get(
    "/api/runs",
    response_model=list[RunSummary],
    summary="파이프라인 run 목록 (영속화된 과거 + 진행 중)",
)
async def list_runs(
    status: str | None = None,
    problem_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[RunSummary]:
    try:
        return backend_client.list_runs(
            status=status, problem_id=problem_id, limit=limit, offset=offset
        )
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


def _enrich_node_tokens(detail: RunDetail) -> RunDetail:
    """LangSmith 인제스트가 끝났으면 노드별 토큰 사용량을 채워 영속화한다.

    스트림 청크엔 토큰이 없어 0으로 저장되므로, 종료된 run의 상세를 열 때 lazy하게 보충.
    조건: LANGSMITH 설정 + trace_id 존재 + 종료 상태 + 토큰이 아직 안 채워진 done LLM 노드 존재.
    **양수 토큰을 찾았을 때만 저장** → LangSmith 인제스트 지연 시 다음 조회에서 자연 재시도(fail-open)."""
    if not os.getenv("LANGSMITH_API_KEY") or not detail.trace_id:
        return detail
    if detail.status not in ("done", "failed"):
        return detail
    ns = detail.node_states or {}
    needs = any(
        NODE_KIND.get(k) == "llm"
        and (ns.get(k) or {}).get("status") == "done"
        and not ((ns.get(k) or {}).get("tokens") or {}).get("total")
        for k in NODE_ORDER
    )
    if not needs:
        return detail

    usage = node_token_usage(detail.trace_id)  # fail-open {}
    if not usage:
        return detail

    changed = False
    for key, tok in usage.items():
        if tok.get("total"):
            cur = ns.setdefault(key, {})
            cur["tokens"] = tok
            changed = True
    if changed:
        detail.node_states = ns
        try:
            backend_client.update_run(detail.id, RunUpdate(node_states=ns))
        except Exception as exc:  # noqa: BLE001 — 저장 실패해도 이번 응답은 보강된 채 반환
            log.warning("run %s 토큰 영속화 실패(무시): %s", detail.id, exc)
    return detail


@router.get(
    "/api/runs/{run_id}",
    response_model=RunDetail,
    summary="파이프라인 run 상세 — node_states 포함 (LangSmith 토큰 lazy 보강)",
    responses={404: {"description": "run 없음"}},
)
async def get_run(run_id: Annotated[str, PathParam(description="run_id")]) -> RunDetail:
    try:
        detail = backend_client.get_run(run_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    # LangSmith 조회는 블로킹이라 스레드풀에서 — 이벤트 루프 점유 방지.
    return await asyncio.to_thread(_enrich_node_tokens, detail)


@router.post(
    "/api/runs/delete",
    summary="선택한 run 일괄 삭제",
    description="body의 ids에 해당하는 run을 삭제. 진행 중 run이면 인메모리 SSE 큐도 정리.",
)
async def bulk_delete_runs(req: RunBulkDeleteRequest) -> dict[str, Any]:
    if not req.ids:
        return {"deleted_count": 0}
    try:
        n = backend_client.delete_runs(req.ids)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    for rid in req.ids:
        _runs.pop(rid, None)
        _run_traces.pop(rid, None)
    return {"deleted_count": n}


@router.delete(
    "/api/runs/{run_id}",
    summary="run 삭제",
    responses={404: {"description": "run 없음"}},
)
async def delete_run(run_id: Annotated[str, PathParam(description="삭제할 run_id")]) -> dict[str, Any]:
    try:
        backend_client.delete_run(run_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    # 라이브 SSE 큐/trace 매핑도 함께 정리 (진행 중 run을 지운 경우)
    _runs.pop(run_id, None)
    _run_traces.pop(run_id, None)
    return {"id": run_id, "deleted": True}


@router.post(
    "/api/runs/{run_id}/retry",
    response_model=RunResponse,
    summary="run 재실행 (새 run_id로 전체 재실행)",
    description=(
        "원본 run의 problem_id·target_count를 그대로 새 run으로 재실행한다. "
        "from_node 부분 재실행은 LangGraph 체크포인트가 필요해 현재는 전체 재실행으로 폴백."
    ),
    responses={404: {"description": "원본 run 없음"}},
)
async def retry_run(
    run_id: Annotated[str, PathParam(description="재실행할 원본 run_id")],
    req: RetryRequest | None = None,
) -> RunResponse:
    try:
        original = backend_client.get_run(run_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    if original.problem_id is None:
        raise HTTPException(400, "원본 run에 problem_id가 없어 재실행할 수 없습니다")
    return _start_run(original.problem_id, original.target_count or 1, original.by_user)


@router.get(
    "/api/runs/{run_id}/events",
    summary="파이프라인 진행 SSE 스트림 (라이브 run 한정)",
)
async def stream_events(
    run_id: Annotated[str, PathParam(description="POST /api/runs가 반환한 run_id")]
):
    q = _runs.get(run_id)
    if q is None:
        raise HTTPException(status_code=404, detail="run not found (live 큐 없음 — 과거 run은 GET /api/runs/{id})")

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
