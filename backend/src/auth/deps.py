"""FastAPI dependency: Supabase Bearer JWT or dev-login cookie → UserRow."""
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .supabase_jwt import verify_supabase_jwt
from ..storage import get_session
from ..storage.models import UserRow
from ..storage.sessions import get_session_user
from ..storage.users import get_or_create_user

import jwt

SESSION_COOKIE = "jcq_session"
_bearer = HTTPBearer(auto_error=False)

ALLOWED_EMAIL_DOMAIN = "jbnu.ac.kr"


def _touch(user: UserRow) -> None:
    _ = (user.id, user.display_name, user.email, user.exp, user.tier, user.provider, user.external_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    jcq_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> UserRow:
    # 1. Supabase Bearer JWT (프로덕션)
    if credentials is not None:
        try:
            payload = verify_supabase_jwt(credentials.credentials)
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않거나 만료된 토큰입니다.",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"JWT 검증 실패: {e}",
            )

        sub = payload.get("sub")
        email = payload.get("email")
        meta = payload.get("user_metadata") or {}
        name = meta.get("full_name") or meta.get("name") or email or "(이름 없음)"

        if not sub:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing sub")

        if not email or not email.lower().endswith(f"@{ALLOWED_EMAIL_DOMAIN}"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"@{ALLOWED_EMAIL_DOMAIN} 도메인 계정만 로그인할 수 있습니다.",
            )

        with get_session() as s:
            user = get_or_create_user(
                s, provider="supabase", external_id=sub,
                display_name=name, email=email,
            )
            _touch(user)
            s.expunge(user)
        return user

    # 2. dev-login 쿠키 (개발/테스트 전용 — JCQ_AUTH_ALLOW_DEV_STUB=1)
    if jcq_session is not None:
        with get_session() as s:
            user = get_session_user(s, jcq_session)
            if user is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
            _touch(user)
            s.expunge(user)
        return user

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
