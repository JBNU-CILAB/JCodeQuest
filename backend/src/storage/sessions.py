"""서버 측 세션 — opaque token PK. logout이 진짜 무효화되는 게 JWT 대비 장점."""
import secrets
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, delete, select

from .models import SessionRow, UserRow


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_token() -> str:
    # 256 bit entropy — 추측 불가. URL-safe base64 → 쿠키 값으로 그대로 OK.
    return secrets.token_urlsafe(32)


def create_session(
    session: Session, *, user_id: int, ttl_days: int
) -> tuple[str, datetime]:
    """token, expires_at 반환."""
    token = _new_token()
    expires_at = _utcnow() + timedelta(days=ttl_days)
    row = SessionRow(id=token, user_id=user_id, expires_at=expires_at)
    session.add(row)
    session.commit()
    return token, expires_at


def get_session_user(session: Session, token: str) -> UserRow | None:
    """토큰 → 유효한 UserRow. 만료/미존재면 None.
    만료된 row는 즉시 정리 (다음 lookup의 비용 줄임)."""
    row = session.get(SessionRow, token)
    if row is None:
        return None

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        # SQLite는 tz를 떨굼 — UTC로 가정 (다른 utcnow 핸들링과 동일 규약)
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _utcnow():
        session.delete(row)
        session.commit()
        return None

    return session.get(UserRow, row.user_id)


def delete_session(session: Session, token: str) -> bool:
    """logout. 존재 여부 무관하게 idempotent. 삭제 발생 시 True."""
    row = session.get(SessionRow, token)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def purge_expired(session: Session) -> int:
    """주기적 cleanup — 만료된 row 일괄 삭제. 운영 cron이나 startup에서 호출."""
    stmt = delete(SessionRow).where(SessionRow.expires_at <= _utcnow())
    result = session.exec(stmt)  # type: ignore[call-overload]
    session.commit()
    return result.rowcount or 0


def list_user_sessions(session: Session, user_id: int) -> list[SessionRow]:
    """선택 — '내 활성 세션 목록' 같은 UI에 쓸 자리."""
    stmt = select(SessionRow).where(
        SessionRow.user_id == user_id,
        SessionRow.expires_at > _utcnow(),
    )
    return list(session.exec(stmt).all())
