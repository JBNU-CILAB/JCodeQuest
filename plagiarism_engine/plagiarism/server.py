"""FastAPI 서버 — 표절 검토 트리거 + admin 검토 큐 프록시.

DB는 backend 단일 소유 — 읽기/쓰기는 /internal/plagiarism/* 위임.
/api/health 외 모든 라우트는 Bearer JCQ_ADMIN_TOKEN 요구(admin dashboard 인바운드).
"""
from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import backend_client, config
from .admin_auth import require_admin
from .pipeline import run_plagiarism

app = FastAPI(
    title="JCodeQuest Plagiarism Engine",
    description="Dolos 구조 유사도 + (Phase 2) 멀티에이전트 판정. DB는 backend에 위임.",
    version="0.1.0",
)

_origins = [o.strip() for o in os.getenv("JCQ_DASHBOARD_ORIGIN", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class RunRequest(BaseModel):
    problem_id: int


class PairUpdate(BaseModel):
    status: str | None = None
    admin_notes: str | None = None


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "enabled": config.ENABLED}


@app.post("/api/plagiarism/runs", dependencies=[Depends(require_admin)], summary="문제별 표절 검토 실행")
def trigger_run(req: RunRequest) -> dict:
    if not config.ENABLED:
        raise HTTPException(503, "plagiarism engine disabled (JCQ_PLAGIARISM_ENABLED=0)")
    run_id = uuid.uuid4().hex  # 즉시 반환용 placeholder; 실제 run_id는 백그라운드가 생성·기록

    def _job() -> None:
        try:
            run_plagiarism(req.problem_id)
        except Exception:  # noqa: BLE001 — run은 내부에서 failed로 마감됨
            pass

    threading.Thread(target=_job, name=f"plag-{req.problem_id}", daemon=True).start()
    return {"accepted": True, "problem_id": req.problem_id, "ticket": run_id}


@app.get("/api/plagiarism/runs", dependencies=[Depends(require_admin)], summary="표절 run 목록")
def list_runs(problem_id: int | None = Query(None), limit: int = Query(100, ge=1, le=200)) -> object:
    params: dict = {"limit": limit}
    if problem_id is not None:
        params["problem_id"] = problem_id
    return backend_client.list_runs(params)


@app.get("/api/plagiarism/pairs", dependencies=[Depends(require_admin)], summary="의심 쌍 검토 큐")
def list_pairs(
    status: str | None = Query(None),
    problem_id: int | None = Query(None),
    run_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> object:
    params: dict = {"limit": limit, "offset": offset}
    for k, v in (("status", status), ("problem_id", problem_id), ("run_id", run_id)):
        if v is not None:
            params[k] = v
    return backend_client.list_pairs(params)


@app.get("/api/plagiarism/pairs/{pair_id}", dependencies=[Depends(require_admin)], summary="의심 쌍 상세(코드 포함)")
def get_pair(pair_id: int = PathParam(...)) -> object:
    code, body = backend_client.get_pair(pair_id)
    if code != 200:
        raise HTTPException(code, body if isinstance(body, str) else "not found")
    return body


@app.patch("/api/plagiarism/pairs/{pair_id}", dependencies=[Depends(require_admin)], summary="검토 상태 갱신")
def update_pair(req: PairUpdate, pair_id: int = PathParam(...)) -> object:
    code, body = backend_client.update_pair(pair_id, req.model_dump(exclude_none=True))
    if code != 200:
        raise HTTPException(code, body if isinstance(body, str) else "update failed")
    return body
