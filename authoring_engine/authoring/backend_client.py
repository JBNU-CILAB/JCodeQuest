"""backend ↔ authoring_engine 내부 API 클라이언트.

backend의 `/internal/*` 라우트는 `Authorization: Bearer <JCQ_INTERNAL_SECRET>`로 인증한다.
DB 접근은 전부 backend가 담당 — authoring_engine은 sys.path 주입 없이 HTTP만 쓴다.
"""
from __future__ import annotations

import logging
import os

import httpx
from jcq_shared.schemas import (
    AuthoringProblemAdmin,
    AuthoringProblemCreate,
    AuthoringProblemCreateResponse,
    AuthoringProblemSummary,
    EmbeddingUpdateRequest,
    ExecResult,
    Problem,
    ProblemDeleteResponse,
    ProblemEmbedding,
    RunCreate,
    RunDetail,
    RunSummary,
    RunUpdate,
    SandboxRunRequest,
)

log = logging.getLogger(__name__)

# 변형 1건 verify에 reference_code를 케이스 수만큼 호출 → 합산 시간이 분 단위로 늘 수 있어
# 충분히 길게. 큐잉이 아니라 동기 호출이므로 hard cap만 안전망 역할.
_DEFAULT_TIMEOUT_S = 120.0


def _backend_url() -> str:
    return os.getenv("JCQ_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _judge_url() -> str:
    return os.getenv("JCQ_JUDGE_URL", "http://127.0.0.1:8002").rstrip("/")


def _auth_headers() -> dict[str, str]:
    secret = os.getenv("JCQ_INTERNAL_SECRET", "")
    if not secret:
        log.warning(
            "JCQ_INTERNAL_SECRET 미설정 — backend가 503으로 거부할 것입니다"
        )
    return {"Authorization": f"Bearer {secret}"}


def _client(timeout_s: float = _DEFAULT_TIMEOUT_S) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(timeout_s), headers=_auth_headers())


# ── backend (/internal/problems) ─────────────────────────────────────────
def fetch_problem(problem_id: int) -> AuthoringProblemAdmin:
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/problems/{problem_id}")
        r.raise_for_status()
        return AuthoringProblemAdmin.model_validate(r.json())


def fetch_seeds(problem_id: int, limit: int = 3) -> list[AuthoringProblemAdmin]:
    with _client() as cli:
        r = cli.get(
            f"{_backend_url()}/internal/problems/{problem_id}/seeds",
            params={"limit": limit},
        )
        r.raise_for_status()
        return [AuthoringProblemAdmin.model_validate(x) for x in r.json()]


def fetch_category_embeddings(problem_id: int) -> list[ProblemEmbedding]:
    """problem_id와 같은 카테고리 approved 문제의 (id, title, embedding) 전체.
    신규성 검사가 후보를 카테고리 형제 전체와 비교할 때의 모집단."""
    with _client() as cli:
        r = cli.get(
            f"{_backend_url()}/internal/problems/{problem_id}/category-embeddings",
        )
        r.raise_for_status()
        return [ProblemEmbedding.model_validate(x) for x in r.json()]


def set_problem_embedding(problem_id: int, embedding: list[float]) -> None:
    """기존 문제 임베딩 백필/갱신."""
    req = EmbeddingUpdateRequest(embedding=embedding)
    with _client() as cli:
        r = cli.patch(
            f"{_backend_url()}/internal/problems/{problem_id}/embedding",
            json=req.model_dump(),
        )
        r.raise_for_status()


def list_problems(originals_only: bool = True) -> list[AuthoringProblemSummary]:
    with _client() as cli:
        r = cli.get(
            f"{_backend_url()}/internal/problems",
            params={"originals_only": str(originals_only).lower()},
        )
        r.raise_for_status()
        return [AuthoringProblemSummary.model_validate(x) for x in r.json()]


def list_children(problem_id: int) -> list[AuthoringProblemAdmin]:
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/problems/{problem_id}/children")
        r.raise_for_status()
        return [AuthoringProblemAdmin.model_validate(x) for x in r.json()]


def create_problem(
    problem: Problem,
    *,
    status: str = "approved",
    parent_id: int | None = None,
    langsmith_trace_id: str | None = None,
    authoring_meta: dict | None = None,
    iso_week: str | None = None,
    embedding: list[float] | None = None,
) -> int:
    req = AuthoringProblemCreate(
        problem=problem,
        status=status,  # type: ignore[arg-type]
        parent_id=parent_id,
        langsmith_trace_id=langsmith_trace_id,
        authoring_meta=authoring_meta,
        iso_week=iso_week,
        embedding=embedding,
    )
    with _client() as cli:
        r = cli.post(
            f"{_backend_url()}/internal/problems",
            json=req.model_dump(),
        )
        r.raise_for_status()
        return AuthoringProblemCreateResponse.model_validate(r.json()).id


def delete_problem(
    problem_id: int,
    *,
    cascade_children: bool = True,
) -> ProblemDeleteResponse:
    with _client() as cli:
        r = cli.delete(
            f"{_backend_url()}/internal/problems/{problem_id}",
            params={"cascade_children": str(cascade_children).lower()},
        )
        r.raise_for_status()
        return ProblemDeleteResponse.model_validate(r.json())


# ── backend (/internal/notices) ──────────────────────────────────────────
def list_notices(*, limit: int = 100) -> list[dict]:
    with _client() as cli:
        r = cli.get(
            f"{_backend_url()}/internal/notices",
            params={"limit": limit},
        )
        r.raise_for_status()
        return r.json()


def create_notice(payload: dict) -> dict:
    with _client() as cli:
        r = cli.post(f"{_backend_url()}/internal/notices", json=payload)
        r.raise_for_status()
        return r.json()


def update_notice(notice_id: int, payload: dict) -> dict:
    with _client() as cli:
        r = cli.patch(
            f"{_backend_url()}/internal/notices/{notice_id}",
            json=payload,
        )
        r.raise_for_status()
        return r.json()


def delete_notice(notice_id: int) -> dict:
    with _client() as cli:
        r = cli.delete(f"{_backend_url()}/internal/notices/{notice_id}")
        r.raise_for_status()
        return r.json()


# ── backend (/internal/reports) ──────────────────────────────────────────
def list_reports(
    *,
    status: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if status is not None:
        params["status"] = status
    if category is not None:
        params["category"] = category
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/reports", params=params)
        r.raise_for_status()
        return r.json()


def get_report(report_id: int) -> dict:
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/reports/{report_id}")
        r.raise_for_status()
        return r.json()


def update_report(report_id: int, payload: dict) -> dict:
    with _client() as cli:
        r = cli.patch(
            f"{_backend_url()}/internal/reports/{report_id}",
            json=payload,
        )
        r.raise_for_status()
        return r.json()


def delete_report(report_id: int) -> dict:
    with _client() as cli:
        r = cli.delete(f"{_backend_url()}/internal/reports/{report_id}")
        r.raise_for_status()
        return r.json()


# ── backend (/internal/runs) — 파이프라인 run 영속화 ─────────────────────
def create_run(req: RunCreate) -> RunSummary:
    with _client(timeout_s=10.0) as cli:
        r = cli.post(f"{_backend_url()}/internal/runs", json=req.model_dump())
        r.raise_for_status()
        return RunSummary.model_validate(r.json())


def update_run(run_id: str, req: RunUpdate) -> RunSummary:
    with _client(timeout_s=10.0) as cli:
        r = cli.patch(
            f"{_backend_url()}/internal/runs/{run_id}",
            json=req.model_dump(exclude_none=True),
        )
        r.raise_for_status()
        return RunSummary.model_validate(r.json())


def list_runs(
    *,
    status: str | None = None,
    problem_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[RunSummary]:
    params: dict[str, object] = {"limit": limit, "offset": offset}
    if status is not None:
        params["status"] = status
    if problem_id is not None:
        params["problem_id"] = problem_id
    with _client(timeout_s=10.0) as cli:
        r = cli.get(f"{_backend_url()}/internal/runs", params=params)
        r.raise_for_status()
        return [RunSummary.model_validate(x) for x in r.json()]


def get_run(run_id: str) -> RunDetail:
    with _client(timeout_s=10.0) as cli:
        r = cli.get(f"{_backend_url()}/internal/runs/{run_id}")
        r.raise_for_status()
        return RunDetail.model_validate(r.json())


# ── judge_engine (/api/sandbox/run) ──────────────────────────────────────
def sandbox_run(
    code: str,
    stdin: str = "",
    *,
    time_limit_ms: int = 2000,
    memory_limit_mb: int = 256,
) -> ExecResult:
    """1회성 sandbox 실행. judge_engine이 backend와 같은 INTERNAL_SECRET을 공유한다."""
    req = SandboxRunRequest(
        code=code,
        stdin=stdin,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
    )
    with _client() as cli:
        r = cli.post(f"{_judge_url()}/api/sandbox/run", json=req.model_dump())
        r.raise_for_status()
        return ExecResult.model_validate(r.json())
