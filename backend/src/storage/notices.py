"""NoticeRow CRUD 헬퍼. API/internal 라우터에서 공용으로 호출."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from .models import NoticeRow


def list_notices(session: Session, *, limit: int = 50) -> list[NoticeRow]:
    """공지 목록 — pinned 우선, 그 다음 created_at 내림차순."""
    stmt = (
        select(NoticeRow)
        .order_by(NoticeRow.pinned.desc(), NoticeRow.created_at.desc())  # type: ignore[union-attr]
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def get_notice(session: Session, notice_id: int) -> NoticeRow | None:
    return session.get(NoticeRow, notice_id)


def create_notice(
    session: Session,
    *,
    title: str,
    body: str,
    pinned: bool = False,
) -> NoticeRow:
    row = NoticeRow(title=title, body=body, pinned=pinned)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def update_notice(
    session: Session,
    notice_id: int,
    *,
    title: str | None = None,
    body: str | None = None,
    pinned: bool | None = None,
) -> NoticeRow | None:
    row = session.get(NoticeRow, notice_id)
    if row is None:
        return None
    if title is not None:
        row.title = title
    if body is not None:
        row.body = body
    if pinned is not None:
        row.pinned = pinned
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def delete_notice(session: Session, notice_id: int) -> bool:
    row = session.get(NoticeRow, notice_id)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True
