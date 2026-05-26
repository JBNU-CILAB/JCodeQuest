"""RunRow CRUD 헬퍼 — 출제 파이프라인 실행 기록. internal 라우터에서 호출."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from .models import RunRow


def create_run(
    session: Session,
    *,
    id: str,
    trace_id: str | None = None,
    problem_id: int | None = None,
    problem_title: str | None = None,
    target_count: int = 0,
    by_user: str | None = None,
) -> RunRow:
    """run 시작 시 1회. 같은 id로 재호출하면 기존 row를 반환(멱등) — 재시도/중복 POST 방어."""
    existing = session.get(RunRow, id)
    if existing is not None:
        return existing
    row = RunRow(
        id=id,
        trace_id=trace_id,
        problem_id=problem_id,
        problem_title=problem_title,
        target_count=target_count,
        by_user=by_user,
        status="running",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def update_run(
    session: Session,
    run_id: str,
    *,
    status: str | None = None,
    failed_at_node: str | None = None,
    total_duration_ms: int | None = None,
    ended_at: str | None = None,
    saved_problem_ids: list[int] | None = None,
    errors: list[str] | None = None,
    node_states: dict | None = None,
) -> RunRow | None:
    """부분 갱신 — None인 필드는 건드리지 않는다. node_states는 전체 교체."""
    row = session.get(RunRow, run_id)
    if row is None:
        return None
    if status is not None:
        row.status = status
    if failed_at_node is not None:
        row.failed_at_node = failed_at_node
    if total_duration_ms is not None:
        row.total_duration_ms = total_duration_ms
    if ended_at is not None:
        # ISO 문자열 → aware datetime (Z 표기 허용)
        try:
            row.ended_at = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            row.ended_at = datetime.now(timezone.utc)
    if saved_problem_ids is not None:
        row.saved_problem_ids = saved_problem_ids
    if errors is not None:
        row.errors = errors
    if node_states is not None:
        row.node_states = node_states
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_runs(
    session: Session,
    *,
    status: str | None = None,
    problem_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[RunRow]:
    """started_at 내림차순. status / problem_id 필터 옵션."""
    stmt = select(RunRow)
    if status is not None:
        stmt = stmt.where(RunRow.status == status)
    if problem_id is not None:
        stmt = stmt.where(RunRow.problem_id == problem_id)
    stmt = stmt.order_by(RunRow.started_at.desc()).offset(offset).limit(limit)  # type: ignore[union-attr]
    return list(session.exec(stmt).all())


def get_run(session: Session, run_id: str) -> RunRow | None:
    return session.get(RunRow, run_id)
