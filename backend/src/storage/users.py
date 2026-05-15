from sqlmodel import Session, select

from . import vault
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


_UNSET: object = object()


def update_user_profile(
    session: Session,
    user_id: int,
    *,
    nickname: str | None | object = _UNSET,
    grade: int | None | object = _UNSET,
    department: str | None | object = _UNSET,
) -> UserRow | None:
    """학년/학과/닉네임을 부분 갱신. 인자 미전달(_UNSET)이면 그 필드는 안 건드림.
    None을 명시적으로 넘기면 해당 필드를 NULL로 비운다."""
    row = session.get(UserRow, user_id)
    if row is None:
        return None

    if nickname is not _UNSET:
        row.nickname = nickname  # type: ignore[assignment]
    if grade is not _UNSET:
        row.grade = grade  # type: ignore[assignment]
    if department is not _UNSET:
        row.department = department  # type: ignore[assignment]

    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_user_api_key(
    session: Session, user_id: int, *, api_key: str | None
) -> UserRow | None:
    """본인 학내 GPT API 키를 Supabase Vault에 저장하고 UserRow엔 UUID만 박는다.
    빈 값으로 호출하면 Vault 행을 지우고 UUID도 비운다."""
    row = session.get(UserRow, user_id)
    if row is None:
        return None

    if not api_key:
        vault.delete_secret(session, row.api_key_secret_id)
        row.api_key_secret_id = None
    else:
        row.api_key_secret_id = vault.store_secret(
            session,
            name=f"jcq_user_{user_id}_api_key",
            value=api_key,
            existing_id=row.api_key_secret_id,
        )
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_user_api_key(session: Session, user_id: int) -> str | None:
    """튜터 호출 시 사용. Vault에서 복호화해서 평문 키를 돌려준다."""
    row = session.get(UserRow, user_id)
    if row is None:
        return None
    return vault.read_secret(session, row.api_key_secret_id)


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
