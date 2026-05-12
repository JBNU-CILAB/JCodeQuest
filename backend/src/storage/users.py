from sqlmodel import Session, select

from .models import UserRow, _utcnow


def get_user(session: Session, user_id: int) -> UserRow | None:
    return session.get(UserRow, user_id)


def get_or_create_user(
    session: Session,
    *,
    provider: str,
    external_id: str,
    display_name: str,
    email: str | None = None,
) -> UserRow:
    """IdP 콜백/스텁이 호출. (provider, external_id)로 멱등."""
    stmt = select(UserRow).where(
        UserRow.provider == provider,
        UserRow.external_id == external_id,
    )
    row = session.exec(stmt).first()
    if row is not None:
        return row

    row = UserRow(
        provider=provider,
        external_id=external_id,
        display_name=display_name,
        email=email,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def bump_user_exp(session: Session, user_id: int, *, delta: int) -> None:
    """save_grading에서 첫 AC 시점에 호출. 같은 트랜잭션 안에서 commit하기 위해
    세션은 호출자가 관리 — 여기선 add만 하고 flush로 끝낸다."""
    if delta <= 0:
        return
    row = session.get(UserRow, user_id)
    if row is None:
        return
    row.exp += delta
    row.updated_at = _utcnow()
    session.add(row)
    session.flush()
