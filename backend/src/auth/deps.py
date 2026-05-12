"""FastAPI dependency: jcq_session 쿠키 → SessionRow → UserRow."""
from fastapi import Cookie, HTTPException, status

from ..storage import get_session
from ..storage.models import UserRow
from ..storage.sessions import get_session_user

SESSION_COOKIE = "jcq_session"


def _unauth(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Cookie"},
    )


def get_current_user(
    jcq_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> UserRow:
    if jcq_session is None:
        raise _unauth("not authenticated")

    with get_session() as s:
        user = get_session_user(s, jcq_session)
        if user is None:
            raise _unauth("invalid or expired session")
        # detach 전에 필요한 컬럼 read 강제 (lazy access 방지)
        _ = (
            user.id, user.display_name, user.email, user.exp,
            user.tier, user.provider, user.external_id,
        )
        s.expunge(user)
    return user
