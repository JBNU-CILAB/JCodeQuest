"""LangSmith 트레이스 스팬 조회."""
from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam

from ..admin_auth import require_admin
from ..api_models import SpansResponse

router = APIRouter(tags=["spans"], dependencies=[Depends(require_admin)])


@router.get(
    "/api/spans/{trace_id}",
    response_model=SpansResponse,
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
