"""backend ↔ judge_engine 내부 API 클라이언트 (submissions 조회 전용).

backend의 `/internal/*` 라우트는 `Authorization: Bearer <JCQ_INTERNAL_SECRET>`로
인증한다. DB 접근은 전부 backend가 담당 — judge_engine은 HTTP로만 통신.
"""
from __future__ import annotations

import logging
import os

import httpx
from jcq_shared.schemas import (
    AdminSubmissionDetail,
    AdminSubmissionSummary,
    AdminUserSummary,
    StatsJudgeResponse,
    StatsVerdictResponse,
    UserDeleteResponse,
)

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 30.0


def _backend_url() -> str:
    return os.getenv("JCQ_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _auth_headers() -> dict[str, str]:
    secret = os.getenv("JCQ_INTERNAL_SECRET", "")
    if not secret:
        log.warning(
            "JCQ_INTERNAL_SECRET 미설정 — backend가 503으로 거부할 것입니다"
        )
    return {"Authorization": f"Bearer {secret}"}


def _client(timeout_s: float = _DEFAULT_TIMEOUT_S) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(timeout_s), headers=_auth_headers())


def list_submissions(
    *,
    user_id: int | None = None,
    problem_id: int | None = None,
    verdict: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AdminSubmissionSummary]:
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    if user_id is not None:
        params["user_id"] = user_id
    if problem_id is not None:
        params["problem_id"] = problem_id
    if verdict is not None:
        params["verdict"] = verdict
    if status is not None:
        params["status"] = status
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/submissions", params=params)
        r.raise_for_status()
        return [AdminSubmissionSummary.model_validate(x) for x in r.json()]


def get_submission(submission_id: int) -> AdminSubmissionDetail:
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/submissions/{submission_id}")
        r.raise_for_status()
        return AdminSubmissionDetail.model_validate(r.json())


def fetch_verdict_stats(
    *,
    bucket: str = "day",
    since: str | None = None,
    until: str | None = None,
    problem_id: int | None = None,
    user_id: int | None = None,
) -> StatsVerdictResponse:
    params: dict[str, str | int] = {"bucket": bucket}
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    if problem_id is not None:
        params["problem_id"] = problem_id
    if user_id is not None:
        params["user_id"] = user_id
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/stats/verdicts", params=params)
        r.raise_for_status()
        return StatsVerdictResponse.model_validate(r.json())


def list_users(
    *,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AdminUserSummary]:
    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    if search is not None:
        params["search"] = search
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/users", params=params)
        r.raise_for_status()
        return [AdminUserSummary.model_validate(x) for x in r.json()]


def delete_user(user_id: int) -> UserDeleteResponse:
    with _client() as cli:
        r = cli.delete(f"{_backend_url()}/internal/users/{user_id}")
        r.raise_for_status()
        return UserDeleteResponse.model_validate(r.json())


def clear_user_api_key(user_id: int) -> dict:
    with _client() as cli:
        r = cli.delete(f"{_backend_url()}/internal/users/{user_id}/api-key")
        r.raise_for_status()
        return r.json()


def fetch_judge_stats(
    *,
    bucket: str = "day",
    since: str | None = None,
    until: str | None = None,
    problem_id: int | None = None,
) -> StatsJudgeResponse:
    params: dict[str, str | int] = {"bucket": bucket}
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    if problem_id is not None:
        params["problem_id"] = problem_id
    with _client() as cli:
        r = cli.get(f"{_backend_url()}/internal/stats/judges", params=params)
        r.raise_for_status()
        return StatsJudgeResponse.model_validate(r.json())
