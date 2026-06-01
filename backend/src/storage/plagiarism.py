"""표절 검토 run/pair CRUD. plagiarism_engine(쓰기)과 admin(/internal/plagiarism, 읽기·갱신)에서 공용."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from .models import PlagiarismPairRow, PlagiarismRunRow, ProblemRow, UserRow

# 같은 두 학생의 같은 문제 쌍을 새 evidence 로 덮어쓸 때 갱신하는 필드.
# status / admin_notes / created_at 은 의도적으로 제외 — 운영자의 판정·이력은 보존.
_PAIR_EVIDENCE_FIELDS = (
    "run_id", "similarity", "longest_fragment", "total_overlap", "fragments",
    "submission_a_id", "submission_b_id", "user_a_id", "user_b_id",
    "agent_verdict", "agent_confidence", "agent_rationale", "agent_debate",
)


# ── run ──────────────────────────────────────────────────────────────────
def create_plagiarism_run(
    session: Session,
    *,
    id: str,
    problem_id: int,
    problem_title: str | None = None,
    submission_count: int = 0,
    config: dict | None = None,
) -> PlagiarismRunRow:
    """run 시작 시 1회. 같은 id 재호출은 멱등(기존 row 반환)."""
    existing = session.get(PlagiarismRunRow, id)
    if existing is not None:
        return existing
    row = PlagiarismRunRow(
        id=id,
        problem_id=problem_id,
        problem_title=problem_title,
        submission_count=submission_count,
        config=config or {},
        status="running",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def update_plagiarism_run(
    session: Session,
    run_id: str,
    *,
    status: str | None = None,
    submission_count: int | None = None,
    pair_count: int | None = None,
    flagged_count: int | None = None,
    ended_at: str | None = None,
    total_duration_ms: int | None = None,
    errors: list[str] | None = None,
) -> PlagiarismRunRow | None:
    row = session.get(PlagiarismRunRow, run_id)
    if row is None:
        return None
    if status is not None:
        row.status = status
    if submission_count is not None:
        row.submission_count = submission_count
    if pair_count is not None:
        row.pair_count = pair_count
    if flagged_count is not None:
        row.flagged_count = flagged_count
    if ended_at is not None:
        try:
            row.ended_at = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            row.ended_at = datetime.now(timezone.utc)
    if total_duration_ms is not None:
        row.total_duration_ms = total_duration_ms
    if errors is not None:
        row.errors = errors
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_plagiarism_runs(
    session: Session, *, problem_id: int | None = None, limit: int = 100, offset: int = 0
) -> list[PlagiarismRunRow]:
    stmt = select(PlagiarismRunRow)
    if problem_id is not None:
        stmt = stmt.where(PlagiarismRunRow.problem_id == problem_id)
    stmt = stmt.order_by(PlagiarismRunRow.started_at.desc()).offset(offset).limit(limit)  # type: ignore[union-attr]
    return list(session.exec(stmt).all())


# ── pairs ────────────────────────────────────────────────────────────────
def insert_plagiarism_pairs(session: Session, pairs: list[dict[str, Any]]) -> list[int]:
    """의심 쌍 upsert. 각 dict는 PlagiarismPairRow 필드 부분집합.

    dedup 키 = (problem_id, {user_a_id, user_b_id}) — 학생 쌍 순서는 정규화해 비교.
    같은 문제·같은 두 학생 쌍이 이미 있으면:
      - status 가 confirmed/dismissed 인 종결 케이스 → 건드리지 않음(재논의 방지).
      - 그 외(open/in_progress) → evidence 필드만 새 run 결과로 덮어쓰고
        status·admin_notes 는 그대로 보존. updated_at 만 갱신.
    이미 없는 쌍이면 새 row 로 insert. 반환은 처리된(insert + update) row id 목록 —
    호출자(run drive)는 이 길이를 flagged_count 로 기록한다.
    """
    inserted: list[PlagiarismPairRow] = []
    affected_ids: list[int] = []
    now = datetime.now(timezone.utc)

    for p in pairs:
        problem_id = int(p["problem_id"])
        u1 = int(p["user_a_id"])
        u2 = int(p["user_b_id"])
        lo, hi = (u1, u2) if u1 <= u2 else (u2, u1)
        existing = session.exec(
            select(PlagiarismPairRow).where(
                PlagiarismPairRow.problem_id == problem_id,
                or_(
                    and_(PlagiarismPairRow.user_a_id == lo, PlagiarismPairRow.user_b_id == hi),
                    and_(PlagiarismPairRow.user_a_id == hi, PlagiarismPairRow.user_b_id == lo),
                ),
            )
        ).first()
        if existing is not None:
            if existing.status in ("confirmed", "dismissed"):
                # 종결 — evidence 도 덮어쓰지 않고 그대로 둔다. 카운트엔 포함.
                if existing.id is not None:
                    affected_ids.append(existing.id)
                continue
            for k in _PAIR_EVIDENCE_FIELDS:
                if k in p:
                    setattr(existing, k, p[k])
            existing.updated_at = now
            session.add(existing)
            if existing.id is not None:
                affected_ids.append(existing.id)
        else:
            row = PlagiarismPairRow(**p)
            session.add(row)
            inserted.append(row)

    session.commit()
    for r in inserted:
        session.refresh(r)
        if r.id is not None:
            affected_ids.append(r.id)
    return affected_ids


def list_plagiarism_pairs_admin(
    session: Session,
    *,
    status: str | None = None,
    problem_id: int | None = None,
    run_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[tuple[PlagiarismPairRow, str | None, str | None, str | None]]:
    """관리자 목록 — (pair, user_a_name, user_b_name, problem_title). 유사도 내림차순."""
    UserA = UserRow
    stmt = select(PlagiarismPairRow).order_by(PlagiarismPairRow.similarity.desc())  # type: ignore[union-attr]
    if status is not None:
        stmt = stmt.where(PlagiarismPairRow.status == status)
    if problem_id is not None:
        stmt = stmt.where(PlagiarismPairRow.problem_id == problem_id)
    if run_id is not None:
        stmt = stmt.where(PlagiarismPairRow.run_id == run_id)
    rows = list(session.exec(stmt.offset(offset).limit(limit)).all())
    # 유저/문제명은 별도 조회(셀프 조인 2회 회피, 목록 규모 작음)
    out: list[tuple[PlagiarismPairRow, str | None, str | None, str | None]] = []
    for r in rows:
        ua = session.get(UserA, r.user_a_id)
        ub = session.get(UserA, r.user_b_id)
        prob = session.get(ProblemRow, r.problem_id)
        out.append((r, ua.display_name if ua else None, ub.display_name if ub else None, prob.title if prob else None))
    return out


def get_plagiarism_pair(session: Session, pair_id: int) -> PlagiarismPairRow | None:
    return session.get(PlagiarismPairRow, pair_id)


def update_plagiarism_pair_admin(
    session: Session,
    pair_id: int,
    *,
    status: str | None = None,
    admin_notes: str | None = None,
) -> PlagiarismPairRow | None:
    row = session.get(PlagiarismPairRow, pair_id)
    if row is None:
        return None
    if status is not None:
        row.status = status
    if admin_notes is not None:
        row.admin_notes = admin_notes
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
