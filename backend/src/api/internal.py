"""내부 서비스 간 통신용 라우터. **공개 인터넷에 노출 금지** — reverse proxy 단에서
`/internal/*` 경로를 차단할 것. 인증은 `Authorization: Bearer <JCQ_INTERNAL_SECRET>`.

엔드포인트:
  POST   /internal/grade-events            judge_engine이 채점 라이프사이클 이벤트를 push
  GET    /internal/problems/{id}           authoring_engine: 원본 문제 상세
  GET    /internal/problems/{id}/seeds     authoring_engine: 같은 카테고리 시드 (approved)
  POST   /internal/problems                authoring_engine: 변형/시드 문제 저장
  DELETE /internal/problems/{id}           admin: 문제 + 변형/제출/튜터 cascade 삭제
  GET    /internal/problems                authoring viewer: 관리자 목록 (변형 통계 포함)
  GET    /internal/problems/{id}/children  authoring viewer: 변형 목록 상세
  GET    /internal/submissions             admin: 제출 목록 (필터 + 페이지네이션)
  GET    /internal/submissions/{id}        admin: 제출 상세 (코드/votes/test_results)
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
    AdminSubmissionDetail,
    AdminSubmissionSummary,
    AuthoringProblemAdmin,
    AuthoringProblemCreate,
    AuthoringProblemCreateResponse,
    AuthoringProblemSummary,
    AuthoringTestCase,
    GradeEvent,
    Notice,
    NoticeCreateRequest,
    NoticeUpdateRequest,
    ProblemDeleteCascade,
    ProblemDeleteResponse,
)
from ..storage import get_session
from ..storage.models import NoticeRow, ProblemRow, SubmissionRow, UserRow, iso_week_of
from ..storage.notices import (
    create_notice,
    delete_notice,
    list_notices,
    update_notice,
)
from ..storage.problems import create_problem, delete_problem

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


@router.delete(
    "/problems/{problem_id}",
    response_model=ProblemDeleteResponse,
    summary="문제 + 변형/제출/튜터 cascade 삭제 (하드)",
    description=(
        "단일 트랜잭션 내에서: 자식 변형(재귀) → tutor_messages → submissions → "
        "test_cases(SQLA cascade) → problem 순으로 삭제. 반환값에 각 카운트가 들어있다."
    ),
    responses={404: {"description": "문제 없음"}},
)
def delete_problem_admin(
    problem_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
    cascade_children: Annotated[bool, Query(description="변형(자식 문제)까지 함께 삭제")] = True,
) -> ProblemDeleteResponse:
    _require_internal_auth(authorization)
    with get_session() as session:
        counts = delete_problem(session, problem_id, cascade_children=cascade_children)
    if counts is None:
        raise HTTPException(404, f"problem {problem_id} not found")
    return ProblemDeleteResponse(id=problem_id, cascade=ProblemDeleteCascade(**counts))


# ── submissions ──────────────────────────────────────────────────────────
def _sub_to_summary(
    s: SubmissionRow,
    user_name: str | None,
    problem_title: str | None,
) -> AdminSubmissionSummary:
    return AdminSubmissionSummary(
        id=s.id,  # type: ignore[arg-type]
        user_id=s.user_id,
        user_display_name=user_name,
        problem_id=s.problem_id,
        problem_title=problem_title,
        status=s.status,
        final_verdict=s.final_verdict,
        mode=s.mode,
        max_elapsed_ms=s.max_elapsed_ms,
        peak_memory_kb=s.peak_memory_kb,
        points_awarded=s.points_awarded,
        created_at=s.created_at.isoformat() if s.created_at else None,
    )


@router.get(
    "/submissions",
    response_model=list[AdminSubmissionSummary],
    summary="제출 목록 (필터 + 페이지네이션)",
)
def list_submissions_admin(
    authorization: Annotated[str | None, Header()] = None,
    user_id: Annotated[int | None, Query()] = None,
    problem_id: Annotated[int | None, Query()] = None,
    verdict: Annotated[str | None, Query(description="AC | SUS")] = None,
    status: Annotated[str | None, Query(description="queued | running | done | failed")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminSubmissionSummary]:
    _require_internal_auth(authorization)
    with get_session() as session:
        # SubmissionRow + UserRow.display_name + ProblemRow.title 를 한 번에.
        stmt = (
            select(SubmissionRow, UserRow.display_name, ProblemRow.title)
            .join(UserRow, UserRow.id == SubmissionRow.user_id)  # type: ignore[arg-type]
            .join(ProblemRow, ProblemRow.id == SubmissionRow.problem_id)  # type: ignore[arg-type]
            .order_by(SubmissionRow.id.desc())  # type: ignore[union-attr]
        )
        if user_id is not None:
            stmt = stmt.where(SubmissionRow.user_id == user_id)
        if problem_id is not None:
            stmt = stmt.where(SubmissionRow.problem_id == problem_id)
        if verdict is not None:
            stmt = stmt.where(SubmissionRow.final_verdict == verdict)
        if status is not None:
            stmt = stmt.where(SubmissionRow.status == status)
        rows = list(session.exec(stmt.offset(offset).limit(limit)).all())
    return [_sub_to_summary(s, name, title) for (s, name, title) in rows]


@router.get(
    "/submissions/{submission_id}",
    response_model=AdminSubmissionDetail,
    summary="제출 상세 (코드/votes/test_results 포함)",
    responses={404: {"description": "제출 없음"}},
)
def get_submission_admin(
    submission_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> AdminSubmissionDetail:
    _require_internal_auth(authorization)
    with get_session() as session:
        s = session.get(SubmissionRow, submission_id)
        if s is None:
            raise HTTPException(404, f"submission {submission_id} not found")
        user = session.get(UserRow, s.user_id)
        problem = session.get(ProblemRow, s.problem_id)
        return AdminSubmissionDetail(
            id=s.id,  # type: ignore[arg-type]
            user_id=s.user_id,
            user_display_name=user.display_name if user else None,
            problem_id=s.problem_id,
            problem_title=problem.title if problem else None,
            status=s.status,
            final_verdict=s.final_verdict,
            mode=s.mode,
            max_elapsed_ms=s.max_elapsed_ms,
            peak_memory_kb=s.peak_memory_kb,
            points_awarded=s.points_awarded,
            created_at=s.created_at.isoformat() if s.created_at else None,
            code=s.code,
            votes=s.votes,
            test_results=s.test_results,
        )


# ── notices ──────────────────────────────────────────────────────────────
def _notice_to_dto(row: NoticeRow) -> Notice:
    assert row.id is not None
    return Notice(
        id=row.id,
        title=row.title,
        body=row.body,
        pinned=row.pinned,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/notices",
    response_model=list[Notice],
    summary="공지 목록 (admin)",
)
def list_notices_admin(
    authorization: Annotated[str | None, Header()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[Notice]:
    _require_internal_auth(authorization)
    with get_session() as session:
        return [_notice_to_dto(r) for r in list_notices(session, limit=limit)]


@router.post(
    "/notices",
    response_model=Notice,
    summary="공지 등록 (admin)",
)
def create_notice_admin(
    req: NoticeCreateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> Notice:
    _require_internal_auth(authorization)
    with get_session() as session:
        row = create_notice(
            session, title=req.title, body=req.body, pinned=req.pinned
        )
    return _notice_to_dto(row)


@router.patch(
    "/notices/{notice_id}",
    response_model=Notice,
    summary="공지 수정 (admin)",
    responses={404: {"description": "공지 없음"}},
)
def update_notice_admin(
    notice_id: Annotated[int, Path()],
    req: NoticeUpdateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> Notice:
    _require_internal_auth(authorization)
    with get_session() as session:
        row = update_notice(
            session,
            notice_id,
            title=req.title,
            body=req.body,
            pinned=req.pinned,
        )
    if row is None:
        raise HTTPException(404, f"notice {notice_id} not found")
    return _notice_to_dto(row)


@router.delete(
    "/notices/{notice_id}",
    summary="공지 삭제 (admin)",
    responses={404: {"description": "공지 없음"}},
)
def delete_notice_admin(
    notice_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    _require_internal_auth(authorization)
    with get_session() as session:
        ok = delete_notice(session, notice_id)
    if not ok:
        raise HTTPException(404, f"notice {notice_id} not found")
    return {"id": notice_id}
