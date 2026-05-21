"""BugReportRow CRUD 헬퍼. 사용자(/reports) + 운영(/internal/reports)에서 공용으로 호출."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from .models import BugReportRow, ProblemRow, UserRow


def create_bug_report(
    session: Session,
    *,
    user_id: int,
    problem_id: int | None,
    category: str,
    title: str,
    body: str,
    code_snapshot: str | None = None,
) -> BugReportRow:
    row = BugReportRow(
        user_id=user_id,
        problem_id=problem_id,
        category=category,
        title=title,
        body=body,
        code_snapshot=code_snapshot,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_bug_reports_admin(
    session: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[BugReportRow, str | None, str | None]]:
    """관리자 목록 — (report, user_display_name, problem_title) 튜플로 반환.
    최신순. status/category 필터 옵션."""
    stmt = (
        select(BugReportRow, UserRow.display_name, ProblemRow.title)
        .join(UserRow, UserRow.id == BugReportRow.user_id)  # type: ignore[arg-type]
        .join(
            ProblemRow,
            ProblemRow.id == BugReportRow.problem_id,  # type: ignore[arg-type]
            isouter=True,
        )
        .order_by(BugReportRow.id.desc())  # type: ignore[union-attr]
    )
    if status is not None:
        stmt = stmt.where(BugReportRow.status == status)
    if category is not None:
        stmt = stmt.where(BugReportRow.category == category)
    return list(session.exec(stmt.offset(offset).limit(limit)).all())  # type: ignore[return-value]


def get_bug_report_admin(
    session: Session, report_id: int
) -> tuple[BugReportRow, str | None, str | None] | None:
    """상세 조회 — code_snapshot 포함, user/problem join."""
    row = session.get(BugReportRow, report_id)
    if row is None:
        return None
    user = session.get(UserRow, row.user_id)
    problem = (
        session.get(ProblemRow, row.problem_id)
        if row.problem_id is not None
        else None
    )
    return (
        row,
        user.display_name if user else None,
        problem.title if problem else None,
    )


def update_bug_report_admin(
    session: Session,
    report_id: int,
    *,
    status: str | None = None,
    admin_notes: str | None = None,
) -> BugReportRow | None:
    row = session.get(BugReportRow, report_id)
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


def delete_bug_report(session: Session, report_id: int) -> bool:
    row = session.get(BugReportRow, report_id)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True
