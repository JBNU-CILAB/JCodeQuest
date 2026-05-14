"""내부 서비스 간 통신용 라우터. **공개 인터넷에 노출 금지** — reverse proxy 단에서
`/internal/*` 경로를 차단할 것. 인증은 `Authorization: Bearer <JCQ_INTERNAL_SECRET>`.

엔드포인트:
  POST /internal/grade-events           judge_engine이 채점 라이프사이클 이벤트를 push
  GET  /internal/problems/{id}          authoring_engine: 원본 문제 상세
  GET  /internal/problems/{id}/seeds    authoring_engine: 같은 카테고리 시드 (approved)
  POST /internal/problems               authoring_engine: 변형/시드 문제 저장
  GET  /internal/problems               authoring viewer: 관리자 목록 (변형 통계 포함)
  GET  /internal/problems/{id}/children authoring viewer: 변형 목록 상세
"""
from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request
from sqlmodel import select

from ..events import SubmissionEventBroker
from ..judge.jobs import apply_grading_event
from ..schemas import (
    AuthoringProblemAdmin,
    AuthoringProblemCreate,
    AuthoringProblemCreateResponse,
    AuthoringProblemSummary,
    AuthoringTestCase,
    GradeEvent,
)
from ..storage import get_session
from ..storage.models import ProblemRow, iso_week_of
from ..storage.problems import create_problem

log = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


def _require_internal_auth(authorization: str | None) -> None:
    secret = os.getenv("JCQ_INTERNAL_SECRET", "")
    if not secret:
        # 시크릿 미설정 시 fail-closed — 잘못 켜 둔 채로 trust 흐름이 흐르지 않도록.
        raise HTTPException(503, "internal endpoint disabled (JCQ_INTERNAL_SECRET unset)")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(None, 1)[1].strip()
    if not hmac.compare_digest(token, secret):
        raise HTTPException(401, "invalid token")


def _row_to_admin(row: ProblemRow) -> AuthoringProblemAdmin:
    return AuthoringProblemAdmin(
        id=row.id,  # type: ignore[arg-type]
        title=row.title,
        statement=row.statement,
        category=row.category,
        level=row.level,  # type: ignore[arg-type]
        points=row.points,
        time_limit_ms=row.time_limit_ms,
        memory_limit_mb=row.memory_limit_mb,
        reference_code=row.reference_code,
        intent_rubric=row.intent_rubric,  # type: ignore[arg-type]
        test_cases=[
            AuthoringTestCase(
                ordinal=t.ordinal,
                stdin=t.stdin,
                expected_stdout=t.expected_stdout,
                is_sample=t.is_sample,
            )
            for t in row.test_cases
        ],
        status=row.status,
        parent_id=row.parent_id,
        langsmith_trace_id=row.langsmith_trace_id,
        authoring_meta=row.authoring_meta,
        iso_week=row.iso_week,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.post(
    "/grade-events",
    summary="judge_engine → backend 채점 이벤트 webhook (내부 전용)",
)
async def grade_events(
    event: GradeEvent,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _require_internal_auth(authorization)
    broker: SubmissionEventBroker = request.app.state.events
    apply_grading_event(event, events=broker)
    return {"status": "ok"}


@router.get(
    "/problems",
    response_model=list[AuthoringProblemSummary],
    summary="authoring viewer용 문제 목록 (변형 통계 포함)",
)
def list_problems_admin(
    authorization: Annotated[str | None, Header()] = None,
    originals_only: Annotated[bool, Query()] = True,
) -> list[AuthoringProblemSummary]:
    _require_internal_auth(authorization)
    with get_session() as session:
        stmt = select(ProblemRow)
        if originals_only:
            stmt = stmt.where(ProblemRow.parent_id.is_(None))  # type: ignore[union-attr]
        rows = list(session.exec(stmt).all())

        # 자식 통계 한 번에 집계
        all_children = list(
            session.exec(
                select(ProblemRow).where(ProblemRow.parent_id.is_not(None))  # type: ignore[union-attr]
            ).all()
        )
        child_stats: dict[int, dict[str, Any]] = {}
        for child in all_children:
            pid = child.parent_id
            if pid is None:
                continue
            bucket = child_stats.setdefault(pid, {"count": 0, "scores": []})
            bucket["count"] += 1
            score = (child.authoring_meta or {}).get("judge_score")
            if isinstance(score, (int, float)):
                bucket["scores"].append(score)

    out: list[AuthoringProblemSummary] = []
    for row in rows:
        stats = child_stats.get(row.id, {"count": 0, "scores": []})  # type: ignore[arg-type]
        scores = stats.get("scores") or []
        out.append(
            AuthoringProblemSummary(
                id=row.id,  # type: ignore[arg-type]
                title=row.title,
                category=row.category,
                level=row.level,  # type: ignore[arg-type]
                status=row.status,
                parent_id=row.parent_id,
                langsmith_trace_id=row.langsmith_trace_id,
                created_at=row.created_at.isoformat() if row.created_at else None,
                child_count=stats["count"],
                avg_judge_score=(sum(scores) / len(scores)) if scores else None,
            )
        )
    return out


@router.get(
    "/problems/{problem_id}",
    response_model=AuthoringProblemAdmin,
    summary="원본 문제 상세 (관리자 시야)",
)
def get_problem_admin(
    problem_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthoringProblemAdmin:
    _require_internal_auth(authorization)
    with get_session() as session:
        row = session.get(ProblemRow, problem_id)
        if row is None:
            raise HTTPException(404, f"problem {problem_id} not found")
        return _row_to_admin(row)


@router.get(
    "/problems/{problem_id}/seeds",
    response_model=list[AuthoringProblemAdmin],
    summary="같은 카테고리의 approved 시드 문제 (해당 ID 제외, 최대 limit개)",
)
def get_problem_seeds(
    problem_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 3,
) -> list[AuthoringProblemAdmin]:
    _require_internal_auth(authorization)
    with get_session() as session:
        target = session.get(ProblemRow, problem_id)
        if target is None:
            raise HTTPException(404, f"problem {problem_id} not found")
        stmt = (
            select(ProblemRow)
            .where(ProblemRow.status == "approved")
            .where(ProblemRow.category == target.category)
            .where(ProblemRow.id != problem_id)  # type: ignore[arg-type]
        )
        rows = list(session.exec(stmt).all())[:limit]
        return [_row_to_admin(r) for r in rows]


@router.get(
    "/problems/{problem_id}/children",
    response_model=list[AuthoringProblemAdmin],
    summary="원본의 변형 목록 (관리자 시야)",
)
def list_problem_children_admin(
    problem_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> list[AuthoringProblemAdmin]:
    _require_internal_auth(authorization)
    with get_session() as session:
        rows = list(
            session.exec(
                select(ProblemRow).where(ProblemRow.parent_id == problem_id)  # type: ignore[arg-type]
            ).all()
        )
        return [_row_to_admin(r) for r in rows]


@router.post(
    "/problems",
    response_model=AuthoringProblemCreateResponse,
    summary="authoring_engine → backend 문제 저장 (변형/시드 공용)",
)
def create_problem_admin(
    req: AuthoringProblemCreate,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthoringProblemCreateResponse:
    _require_internal_auth(authorization)

    issued_week = req.iso_week or iso_week_of(datetime.now(timezone.utc))
    with get_session() as session:
        pid = create_problem(
            session,
            req.problem,
            status=req.status,
            parent_id=req.parent_id,
            langsmith_trace_id=req.langsmith_trace_id,
            authoring_meta=req.authoring_meta,
            iso_week=issued_week,
        )
    return AuthoringProblemCreateResponse(id=pid)
