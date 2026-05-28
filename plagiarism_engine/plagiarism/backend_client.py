"""backend /internal/* 위임 클라이언트 — DB 단일 소유 원칙. Bearer JCQ_INTERNAL_SECRET."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from . import config

log = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    if not config.INTERNAL_SECRET:
        log.warning("JCQ_INTERNAL_SECRET 미설정 — backend가 503으로 거부할 것")
    return {"Authorization": f"Bearer {config.INTERNAL_SECRET}"}


def _client(timeout_s: float = 15.0) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(timeout_s), headers=_headers())


# ── 읽기 ──
def list_ac_submissions(problem_id: int, verdict: str = "AC") -> list[dict[str, Any]]:
    """문제의 제출(코드 포함). [{submission_id, user_id, code, created_at}]."""
    with _client() as c:
        r = c.get(
            f"{config.BACKEND_URL}/internal/problems/{problem_id}/submissions",
            params={"verdict": verdict},
        )
        r.raise_for_status()
        return r.json()


def fetch_problem(problem_id: int) -> dict[str, Any] | None:
    """문제 상세(intent_rubric 포함) — 의미 검토 에이전트의 '문제 의도' 컨텍스트용."""
    with _client() as c:
        r = c.get(f"{config.BACKEND_URL}/internal/problems/{problem_id}")
        if r.status_code != 200:
            return None
        return r.json()


def problem_title(problem_id: int) -> str | None:
    prob = fetch_problem(problem_id)
    return prob.get("title") if prob else None


# ── 쓰기 (엔진 → backend) ──
def create_run(payload: dict[str, Any]) -> dict[str, Any]:
    with _client() as c:
        r = c.post(f"{config.BACKEND_URL}/internal/plagiarism/runs", json=payload)
        r.raise_for_status()
        return r.json()


def update_run(run_id: str, **fields: Any) -> dict[str, Any]:
    body = {k: v for k, v in fields.items() if v is not None}
    with _client() as c:
        r = c.patch(f"{config.BACKEND_URL}/internal/plagiarism/runs/{run_id}", json=body)
        r.raise_for_status()
        return r.json()


def insert_pairs(pairs: list[dict[str, Any]]) -> list[int]:
    if not pairs:
        return []
    with _client() as c:
        r = c.post(f"{config.BACKEND_URL}/internal/plagiarism/pairs", json={"pairs": pairs})
        r.raise_for_status()
        return r.json().get("ids", [])


# ── 프록시 (admin dashboard ↔ backend, server.py가 사용) ──
def list_runs(params: dict[str, Any]) -> Any:
    with _client() as c:
        r = c.get(f"{config.BACKEND_URL}/internal/plagiarism/runs", params=params)
        r.raise_for_status()
        return r.json()


def list_pairs(params: dict[str, Any]) -> Any:
    with _client() as c:
        r = c.get(f"{config.BACKEND_URL}/internal/plagiarism/pairs", params=params)
        r.raise_for_status()
        return r.json()


def get_pair(pair_id: int) -> tuple[int, Any]:
    with _client() as c:
        r = c.get(f"{config.BACKEND_URL}/internal/plagiarism/pairs/{pair_id}")
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


def update_pair(pair_id: int, payload: dict[str, Any]) -> tuple[int, Any]:
    with _client() as c:
        r = c.patch(f"{config.BACKEND_URL}/internal/plagiarism/pairs/{pair_id}", json=payload)
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
