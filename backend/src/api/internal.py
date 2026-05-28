"""내부 서비스 간 통신용 라우터. **공개 인터넷에 노출 금지** — reverse proxy 단에서
`/internal/*` 경로를 차단할 것. 인증은 `Authorization: Bearer <JCQ_INTERNAL_SECRET>`.

엔드포인트:
  POST   /internal/grade-events            judge_engine이 채점 라이프사이클 이벤트를 push
  GET    /internal/problems/{id}           authoring_engine: 원본 문제 상세
  GET    /internal/problems/{id}/seeds     authoring_engine: 같은 카테고리 시드 (approved)
  GET    /internal/problems/{id}/category-embeddings  authoring_engine: 신규성 검사용 임베딩
  PATCH  /internal/problems/{id}/embedding authoring_engine: 임베딩 백필/갱신
  POST   /internal/problems                authoring_engine: 변형/시드 문제 저장
  PATCH  /internal/problems/{id}           admin: 문제 부분 수정 (test_cases 포함)
  DELETE /internal/problems/{id}           admin: 문제 + 변형/제출/튜터 cascade 삭제
  GET    /internal/problems                authoring viewer: 관리자 목록 (변형 통계 포함)
  GET    /internal/problems/{id}/children  authoring viewer: 변형 목록 상세
  GET    /internal/submissions             admin: 제출 목록 (필터 + 페이지네이션)
  GET    /internal/submissions/{id}        admin: 제출 상세 (코드/votes/test_results)
  GET    /internal/users                   admin: 유저 목록 (검색 + 페이지네이션)
  DELETE /internal/users/{id}              admin: 유저 + submission/tutor/session cascade 삭제
  DELETE /internal/users/{id}/api-key      admin: 유저 API 키 강제 제거 (vault row 포함)
"""
from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request
from pydantic import BaseModel
from sqlmodel import select

from ..events import SubmissionEventBroker
from ..judge.jobs import apply_grading_event
from ..schemas import (
    AdminSubmissionDetail,
    AdminSubmissionSummary,
    AdminUserSummary,
    AuthoringProblemAdmin,
    AuthoringProblemCreate,
    AuthoringProblemCreateResponse,
    AuthoringProblemSummary,
    AuthoringProblemUpdate,
    AuthoringTestCase,
    BugReport,
    BugReportUpdateRequest,
    EmbeddingUpdateRequest,
    GradeEvent,
    Notice,
    NoticeCreateRequest,
    NoticeUpdateRequest,
    ProblemDeleteCascade,
    ProblemDeleteResponse,
    ProblemEmbedding,
    RunCreate,
    RunDetail,
    RunSummary,
    RunUpdate,
    StatsJudgeBucket,
    StatsJudgeBucketEntry,
    StatsJudgeResponse,
    StatsVerdictBucket,
    StatsVerdictResponse,
    UserDeleteCascade,
    UserDeleteResponse,
)
from ..storage import get_session
from ..storage.bug_reports import (
    delete_bug_report,
    get_bug_report_admin,
    list_bug_reports_admin,
    update_bug_report_admin,
)
from ..storage.models import (
    BugReportRow,
    NoticeRow,
    ProblemRow,
    RunRow,
    SubmissionRow,
    UserRow,
    iso_week_of,
)
from ..storage.notices import (
    create_notice,
    delete_notice,
    list_notices,
    update_notice,
)
from ..storage.problems import (
    create_problem,
    delete_problem,
    list_category_embeddings,
    set_problem_embedding,
    update_problem,
)
from ..storage.runs import (
    create_run,
    delete_run,
    delete_runs_by_ids,
    get_run,
    list_runs,
    update_run,
)
from ..storage.users import clear_user_api_key, delete_user, list_users_admin

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
    "/problems/{problem_id}/category-embeddings",
    response_model=list[ProblemEmbedding],
    summary="같은 카테고리 approved 문제의 저장된 임베딩 (신규성 검사 모집단, 해당 ID 제외)",
)
def get_category_embeddings(
    problem_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> list[ProblemEmbedding]:
    """출제 엔진의 신규성(중복) 검사가 후보를 카테고리 형제 전체와 비교할 때 쓴다.
    seeds(최대 3개)와 달리 limit 없이 카테고리 전체를 돌려준다 — 모든 형제와 비교해야
    중복을 놓치지 않기 때문. embedding이 NULL인(미백필) 문제도 포함하며 호출 측이 건너뛴다."""
    _require_internal_auth(authorization)
    with get_session() as session:
        rows = list_category_embeddings(session, problem_id)
    if rows is None:
        raise HTTPException(404, f"problem {problem_id} not found")
    return [
        ProblemEmbedding(
            id=rid, title=title, embedding=emb, level=level, judge_score=score
        )
        for rid, title, emb, level, score in rows
    ]


@router.patch(
    "/problems/{problem_id}/embedding",
    summary="기존 문제 임베딩 백필/갱신",
)
def patch_problem_embedding(
    problem_id: Annotated[int, Path()],
    req: EmbeddingUpdateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    _require_internal_auth(authorization)
    with get_session() as session:
        ok = set_problem_embedding(session, problem_id, req.embedding)
    if not ok:
        raise HTTPException(404, f"problem {problem_id} not found")
    return {"id": problem_id}


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
            embedding=req.embedding,
        )
    return AuthoringProblemCreateResponse(id=pid)


@router.patch(
    "/problems/{problem_id}",
    response_model=AuthoringProblemAdmin,
    summary="문제 부분 수정 (admin)",
    description=(
        "주어진 필드만 갱신. test_cases가 포함되면 기존 테스트 케이스를 전체 교체한다 "
        "(cascade delete-orphan). intent_rubric도 통째 교체."
    ),
    responses={404: {"description": "문제 없음"}},
)
def patch_problem_admin(
    problem_id: Annotated[int, Path()],
    req: AuthoringProblemUpdate,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthoringProblemAdmin:
    _require_internal_auth(authorization)
    # 스칼라 필드만 setattr — intent_rubric/test_cases는 별도 처리.
    scalar = req.model_dump(
        exclude_unset=True,
        exclude={"intent_rubric", "test_cases"},
    )
    with get_session() as session:
        ok = update_problem(
            session,
            problem_id,
            fields=scalar,
            intent_rubric=req.intent_rubric,
            test_cases=req.test_cases,
        )
        if not ok:
            raise HTTPException(404, f"problem {problem_id} not found")
        row = session.get(ProblemRow, problem_id)
        assert row is not None
        return _row_to_admin(row)


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


# ── users (admin) ─────────────────────────────────────────────────────
def _user_to_summary(row: UserRow, submission_count: int) -> AdminUserSummary:
    return AdminUserSummary(
        id=row.id,  # type: ignore[arg-type]
        display_name=row.display_name,
        email=row.email,
        provider=row.provider,
        nickname=row.nickname,
        exp=row.exp,
        tier=row.tier,
        has_api_key=row.api_key_secret_id is not None,
        submission_count=submission_count,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.get(
    "/users",
    response_model=list[AdminUserSummary],
    summary="유저 목록 (admin)",
)
def list_users(
    authorization: Annotated[str | None, Header()] = None,
    search: Annotated[str | None, Query(description="display_name/email/nickname 부분 일치")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminUserSummary]:
    _require_internal_auth(authorization)
    with get_session() as session:
        rows = list_users_admin(session, search=search, limit=limit, offset=offset)
    return [_user_to_summary(u, c) for (u, c) in rows]


@router.delete(
    "/users/{user_id}",
    response_model=UserDeleteResponse,
    summary="유저 + submission/tutor/session cascade 삭제 (하드)",
    description=(
        "단일 트랜잭션 내에서: tutor_messages → submissions → sessions → "
        "vault.secret (api_key) → user 순으로 삭제. 카운트가 응답에 포함."
    ),
    responses={404: {"description": "유저 없음"}},
)
def delete_user_admin(
    user_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> UserDeleteResponse:
    _require_internal_auth(authorization)
    with get_session() as session:
        counts = delete_user(session, user_id)
    if counts is None:
        raise HTTPException(404, f"user {user_id} not found")
    return UserDeleteResponse(id=user_id, cascade=UserDeleteCascade(**counts))


@router.delete(
    "/users/{user_id}/api-key",
    summary="유저 API 키 강제 제거 (admin)",
    description=(
        "vault.secrets의 행도 함께 삭제. 키가 없던 유저에 대해서도 200 (idempotent). "
        "유저 자체는 보존되어 본인이 다시 등록 가능."
    ),
    responses={404: {"description": "유저 없음"}},
)
def force_clear_api_key(
    user_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, int | bool]:
    _require_internal_auth(authorization)
    with get_session() as session:
        ok = clear_user_api_key(session, user_id)
    if not ok:
        raise HTTPException(404, f"user {user_id} not found")
    return {"id": user_id, "cleared": True}


# ── stats (admin_dashboard 그래프용) ──────────────────────────────────
# 시계열은 Python 측에서 bucket key 계산 + zero-fill해서 응답한다.
# 이유: SQLite(테스트)와 PostgreSQL(운영)에서 date_trunc/strftime이 갈리는데,
# 우리 submissions 볼륨(목표: 수십만 행 미만)에선 raw fetch + Python aggregation이
# 충분히 빠르고 dialect 분기가 사라진다. 무거워지면 SQL aggregation으로 이동.

_VERDICT_RANGE_CAPS_DAYS = {"hour": 14, "day": 180, "week": 730}


def _bucket_key(dt: datetime, bucket: str) -> str:
    if bucket == "hour":
        return dt.strftime("%Y-%m-%dT%H:00Z")
    if bucket == "day":
        return dt.strftime("%Y-%m-%d")
    if bucket == "week":
        y, w, _ = dt.isocalendar()
        return f"{y}-W{w:02d}"
    raise ValueError(f"invalid bucket: {bucket}")


def _iter_bucket_keys(since: datetime, until: datetime, bucket: str) -> list[str]:
    """[since, until] 구간을 bucket 단위로 끊어 키 시퀀스 생성 (zero-fill용)."""
    from datetime import timedelta

    keys: list[str] = []
    seen: set[str] = set()
    if bucket == "hour":
        step = timedelta(hours=1)
        cur = since.replace(minute=0, second=0, microsecond=0)
    elif bucket == "day":
        step = timedelta(days=1)
        cur = since.replace(hour=0, minute=0, second=0, microsecond=0)
    elif bucket == "week":
        step = timedelta(days=1)  # 일 단위로 진행하며 key dedup
        cur = since.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"invalid bucket: {bucket}")

    while cur <= until:
        k = _bucket_key(cur, bucket)
        if k not in seen:
            keys.append(k)
            seen.add(k)
        cur = cur + step
    return keys


def _parse_range(
    since: datetime | None, until: datetime | None, bucket: str
) -> tuple[datetime, datetime]:
    """query param 정규화 — naïve를 UTC로 보고, 기본 범위 = 최근 14일."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    if until is None:
        until = now
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if since is None:
        since = until - timedelta(days=14)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    if since > until:
        raise HTTPException(400, "since > until")
    cap_days = _VERDICT_RANGE_CAPS_DAYS.get(bucket, 30)
    span_days = (until - since).total_seconds() / 86400
    if span_days > cap_days:
        raise HTTPException(
            400,
            f"range too wide: {span_days:.1f}d > cap {cap_days}d for bucket={bucket}",
        )
    return since, until


@router.get(
    "/stats/verdicts",
    response_model=StatsVerdictResponse,
    summary="시계열 판정 카운트 (A — admin 그래프용)",
    description=(
        "버킷별로 AC / SUS / failed / pending(queued+running) / total을 집계한다. "
        "기본 범위는 최근 14일, until=now (UTC). zero-fill되어 series 길이는 "
        "bucket 단위의 [since, until] 길이와 동일."
    ),
)
def stats_verdicts(
    authorization: Annotated[str | None, Header()] = None,
    bucket: Annotated[str, Query(pattern="^(hour|day|week)$")] = "day",
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    problem_id: Annotated[int | None, Query()] = None,
    user_id: Annotated[int | None, Query()] = None,
) -> StatsVerdictResponse:
    _require_internal_auth(authorization)
    since_dt, until_dt = _parse_range(since, until, bucket)

    with get_session() as session:
        stmt = (
            select(
                SubmissionRow.created_at,
                SubmissionRow.final_verdict,
                SubmissionRow.status,
            )
            .where(SubmissionRow.created_at >= since_dt)
            .where(SubmissionRow.created_at <= until_dt)
        )
        if problem_id is not None:
            stmt = stmt.where(SubmissionRow.problem_id == problem_id)
        if user_id is not None:
            stmt = stmt.where(SubmissionRow.user_id == user_id)
        rows = list(session.exec(stmt).all())

    buckets: dict[str, StatsVerdictBucket] = {
        k: StatsVerdictBucket(bucket=k)
        for k in _iter_bucket_keys(since_dt, until_dt, bucket)
    }
    for created_at, verdict, status_ in rows:
        if created_at is None:
            continue
        # SQLite는 naïve datetime을 돌려준다 — UTC로 가정.
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        key = _bucket_key(created_at, bucket)
        b = buckets.get(key)
        if b is None:
            # 범위 밖 (clock skew 등) — 생성해 추가.
            b = StatsVerdictBucket(bucket=key)
            buckets[key] = b
        b.total += 1
        if status_ == "failed":
            b.failed += 1
        elif status_ in ("queued", "running"):
            b.pending += 1
        elif verdict == "AC":
            b.ac += 1
        elif verdict == "SUS":
            b.sus += 1

    series = sorted(buckets.values(), key=lambda x: x.bucket)
    return StatsVerdictResponse(
        bucket=bucket,  # type: ignore[arg-type]
        since=since_dt.isoformat(),
        until=until_dt.isoformat(),
        series=series,
    )


@router.get(
    "/stats/judges",
    response_model=StatsJudgeResponse,
    summary="시계열 모델별 투표 추세 (B — admin 그래프용)",
    description=(
        "votes JSON을 펼쳐서 judge_id별 AC/SUS 카운트와 최종 판정과의 동의율을 "
        "버킷별로 누적한다. ensemble이 돌지 않은 제출(votes=None)은 제외. "
        "split = 2:1 갈린 제출 수, unanimous = 3:0 합의 제출 수."
    ),
)
def stats_judges(
    authorization: Annotated[str | None, Header()] = None,
    bucket: Annotated[str, Query(pattern="^(hour|day|week)$")] = "day",
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    problem_id: Annotated[int | None, Query()] = None,
) -> StatsJudgeResponse:
    _require_internal_auth(authorization)
    since_dt, until_dt = _parse_range(since, until, bucket)

    with get_session() as session:
        stmt = (
            select(
                SubmissionRow.created_at,
                SubmissionRow.final_verdict,
                SubmissionRow.votes,
            )
            .where(SubmissionRow.created_at >= since_dt)
            .where(SubmissionRow.created_at <= until_dt)
            .where(SubmissionRow.votes.is_not(None))  # type: ignore[union-attr]
        )
        if problem_id is not None:
            stmt = stmt.where(SubmissionRow.problem_id == problem_id)
        rows = list(session.exec(stmt).all())

    buckets: dict[str, StatsJudgeBucket] = {
        k: StatsJudgeBucket(bucket=k)
        for k in _iter_bucket_keys(since_dt, until_dt, bucket)
    }
    judge_ids: set[str] = set()

    for created_at, final_verdict, votes in rows:
        if created_at is None or not isinstance(votes, list) or not votes:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        key = _bucket_key(created_at, bucket)
        b = buckets.get(key)
        if b is None:
            b = StatsJudgeBucket(bucket=key)
            buckets[key] = b
        b.total_with_votes += 1

        verdicts_seen: list[str] = []
        for v in votes:
            if not isinstance(v, dict):
                continue
            jid = v.get("judge_id")
            vd = v.get("verdict")
            if not isinstance(jid, str) or vd not in ("AC", "SUS"):
                continue
            judge_ids.add(jid)
            entry = b.judges.get(jid)
            if entry is None:
                entry = StatsJudgeBucketEntry()
                b.judges[jid] = entry
            if vd == "AC":
                entry.ac += 1
            else:
                entry.sus += 1
            if vd == final_verdict:
                entry.agree_with_final += 1
            verdicts_seen.append(vd)

        if verdicts_seen and len(set(verdicts_seen)) == 1:
            b.unanimous += 1
        elif verdicts_seen:
            b.split += 1

    # 각 버킷에 관측된 judge_id가 빠져 있으면 0 엔트리로 채움 — 그래프 dataset 안정성.
    sorted_ids = sorted(judge_ids)
    for b in buckets.values():
        for jid in sorted_ids:
            if jid not in b.judges:
                b.judges[jid] = StatsJudgeBucketEntry()

    series = sorted(buckets.values(), key=lambda x: x.bucket)
    return StatsJudgeResponse(
        bucket=bucket,  # type: ignore[arg-type]
        since=since_dt.isoformat(),
        until=until_dt.isoformat(),
        judge_ids=sorted_ids,
        series=series,
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


# ── bug reports (admin) ──────────────────────────────────────────────────
def _report_to_dto(
    row: BugReportRow,
    user_name: str | None,
    problem_title: str | None,
) -> BugReport:
    assert row.id is not None
    return BugReport(
        id=row.id,
        user_id=row.user_id,
        user_display_name=user_name,
        problem_id=row.problem_id,
        problem_title=problem_title,
        category=row.category,  # type: ignore[arg-type]
        title=row.title,
        body=row.body,
        code_snapshot=row.code_snapshot,
        status=row.status,  # type: ignore[arg-type]
        admin_notes=row.admin_notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/reports",
    response_model=list[BugReport],
    summary="버그 제보 목록 (admin)",
    description="최신순. status/category 필터 + 페이지네이션. code_snapshot 포함.",
)
def list_reports_admin(
    authorization: Annotated[str | None, Header()] = None,
    status: Annotated[
        str | None, Query(description="open | in_progress | resolved | rejected")
    ] = None,
    category: Annotated[
        str | None,
        Query(description="judging | statement | sample | system | other"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BugReport]:
    _require_internal_auth(authorization)
    with get_session() as session:
        rows = list_bug_reports_admin(
            session,
            status=status,
            category=category,
            limit=limit,
            offset=offset,
        )
    return [_report_to_dto(r, u, p) for (r, u, p) in rows]


@router.get(
    "/reports/{report_id}",
    response_model=BugReport,
    summary="버그 제보 상세 (admin)",
    responses={404: {"description": "제보 없음"}},
)
def get_report_admin(
    report_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> BugReport:
    _require_internal_auth(authorization)
    with get_session() as session:
        result = get_bug_report_admin(session, report_id)
    if result is None:
        raise HTTPException(404, f"report {report_id} not found")
    return _report_to_dto(*result)


@router.patch(
    "/reports/{report_id}",
    response_model=BugReport,
    summary="버그 제보 상태/메모 수정 (admin)",
    responses={404: {"description": "제보 없음"}},
)
def update_report_admin(
    report_id: Annotated[int, Path()],
    req: BugReportUpdateRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> BugReport:
    _require_internal_auth(authorization)
    with get_session() as session:
        updated = update_bug_report_admin(
            session,
            report_id,
            status=req.status,
            admin_notes=req.admin_notes,
        )
        if updated is None:
            raise HTTPException(404, f"report {report_id} not found")
        # 갱신 후 user/problem 다시 join — DTO 일관성.
        result = get_bug_report_admin(session, report_id)
    assert result is not None
    return _report_to_dto(*result)


@router.delete(
    "/reports/{report_id}",
    summary="버그 제보 삭제 (admin)",
    responses={404: {"description": "제보 없음"}},
)
def delete_report_admin(
    report_id: Annotated[int, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, int]:
    _require_internal_auth(authorization)
    with get_session() as session:
        ok = delete_bug_report(session, report_id)
    if not ok:
        raise HTTPException(404, f"report {report_id} not found")
    return {"id": report_id}


# ── 출제 파이프라인 runs (admin RunsView · forensics) ────────────────────────
def _dt_iso(dt: datetime | None) -> str | None:
    """aware/naive 무관 ISO8601 문자열. naive면 UTC로 가정."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _run_to_summary(row: RunRow) -> RunSummary:
    return RunSummary(
        id=row.id,
        trace_id=row.trace_id,
        problem_id=row.problem_id,
        problem_title=row.problem_title,
        target_count=row.target_count,
        by_user=row.by_user,
        status=row.status,
        failed_at_node=row.failed_at_node,
        started_at=_dt_iso(row.started_at),
        ended_at=_dt_iso(row.ended_at),
        total_duration_ms=row.total_duration_ms,
        saved_count=len(row.saved_problem_ids or []),
    )


def _run_to_detail(row: RunRow) -> RunDetail:
    return RunDetail(
        **_run_to_summary(row).model_dump(),
        node_states=row.node_states or {},
        saved_problem_ids=row.saved_problem_ids or [],
        errors=row.errors or [],
    )


@router.post(
    "/runs",
    response_model=RunSummary,
    summary="파이프라인 run 기록 생성 (authoring_engine)",
    description="run 시작 시 1회. 같은 id 재호출은 멱등 — 기존 row 반환.",
)
def create_run_record(
    req: RunCreate,
    authorization: Annotated[str | None, Header()] = None,
) -> RunSummary:
    _require_internal_auth(authorization)
    with get_session() as session:
        row = create_run(
            session,
            id=req.id,
            trace_id=req.trace_id,
            problem_id=req.problem_id,
            problem_title=req.problem_title,
            target_count=req.target_count,
            by_user=req.by_user,
        )
        return _run_to_summary(row)


@router.patch(
    "/runs/{run_id}",
    response_model=RunSummary,
    summary="파이프라인 run 기록 갱신 (authoring_engine)",
    responses={404: {"description": "run 없음"}},
)
def update_run_record(
    run_id: Annotated[str, Path()],
    req: RunUpdate,
    authorization: Annotated[str | None, Header()] = None,
) -> RunSummary:
    _require_internal_auth(authorization)
    with get_session() as session:
        row = update_run(
            session,
            run_id,
            status=req.status,
            failed_at_node=req.failed_at_node,
            total_duration_ms=req.total_duration_ms,
            ended_at=req.ended_at,
            saved_problem_ids=req.saved_problem_ids,
            errors=req.errors,
            node_states=req.node_states,
        )
        if row is None:
            raise HTTPException(404, f"run {run_id} not found")
        return _run_to_summary(row)


@router.get(
    "/runs",
    response_model=list[RunSummary],
    summary="파이프라인 run 목록 (admin)",
    description="started_at 내림차순. status(running|done|failed) / problem_id 필터 + 페이지네이션.",
)
def list_runs_admin(
    authorization: Annotated[str | None, Header()] = None,
    status: Annotated[str | None, Query(description="running | done | failed")] = None,
    problem_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RunSummary]:
    _require_internal_auth(authorization)
    with get_session() as session:
        rows = list_runs(
            session,
            status=status,
            problem_id=problem_id,
            limit=limit,
            offset=offset,
        )
        return [_run_to_summary(r) for r in rows]


@router.get(
    "/runs/{run_id}",
    response_model=RunDetail,
    summary="파이프라인 run 상세 — node_states 포함 (admin)",
    responses={404: {"description": "run 없음"}},
)
def get_run_admin(
    run_id: Annotated[str, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> RunDetail:
    _require_internal_auth(authorization)
    with get_session() as session:
        row = get_run(session, run_id)
        if row is None:
            raise HTTPException(404, f"run {run_id} not found")
        return _run_to_detail(row)


class _RunBulkDeleteReq(BaseModel):
    ids: list[str]


@router.post(
    "/runs/delete",
    summary="선택한 run 일괄 삭제 (admin)",
    description="body의 ids에 해당하는 run을 삭제하고 삭제 건수를 반환.",
)
def bulk_delete_runs(
    req: _RunBulkDeleteReq,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_internal_auth(authorization)
    with get_session() as session:
        n = delete_runs_by_ids(session, req.ids)
        return {"deleted_count": n}


@router.delete(
    "/runs/{run_id}",
    summary="파이프라인 run 삭제 (admin)",
    responses={404: {"description": "run 없음"}},
)
def delete_run_record(
    run_id: Annotated[str, Path()],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _require_internal_auth(authorization)
    with get_session() as session:
        if not delete_run(session, run_id):
            raise HTTPException(404, f"run {run_id} not found")
        return {"id": run_id, "deleted": True}
