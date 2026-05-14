"""서버 측 세션 관리 라우터.

Supabase가 Google OAuth를 담당하므로, 이 라우터는 logout과 dev stub만 처리한다.
실제 인증은 frontend의 supabase.auth.signInWithOAuth 와 Bearer JWT로 이뤄진다.
"""
import os
from typing import Annotated

from fastapi import APIRouter, Cookie, Response

from ..auth.deps import SESSION_COOKIE
from ..storage import get_session
from ..storage.sessions import create_session, delete_session
from ..storage.users import get_or_create_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _ttl_days() -> int:
    return int(os.getenv("JCQ_SESSION_DAYS", "7"))


def _is_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _issue_session_cookie(response: Response, user_id: int) -> None:
    with get_session() as s:
        token, _expires_at = create_session(s, user_id=user_id, ttl_days=_ttl_days())
    secure = not _is_truthy(os.getenv("JCQ_COOKIE_INSECURE"))
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=_ttl_days() * 86400,
        path="/",
    )


@router.post("/logout")
def logout(
    response: Response,
    jcq_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, str]:
    """dev-login 쿠키 세션을 무효화. Supabase 세션은 frontend에서 signOut()으로 처리."""
    if jcq_session:
        with get_session() as s:
            delete_session(s, jcq_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged out"}


# ───────────────────────── dev stub ─────────────────────────

if _is_truthy(os.getenv("JCQ_AUTH_ALLOW_DEV_STUB")):
    from fastapi import Query

    @router.post(
        "/dev-login",
        summary="dev stub 로그인 (개발 전용)",
        description=(
            "JCQ_AUTH_ALLOW_DEV_STUB=1 일 때만 등록되는 라우트. "
            "OAuth 왕복 없이 즉시 jcq_session 쿠키를 발급한다. 프로덕션 금지."
        ),
    )
    def dev_login(
        response: Response,
        email: Annotated[
            str, Query(description="dev_stub 유저 이메일", examples=["foo@example.com"])
        ],
        name: Annotated[
            str, Query(description="표시 이름")
        ] = "dev user",
    ) -> dict[str, int]:
        with get_session() as s:
            user = get_or_create_user(
                s, provider="dev_stub", external_id=email,
                display_name=name, email=email,
            )
            user_id = user.id
        assert user_id is not None
        _issue_session_cookie(response, user_id)
        return {"user_id": user_id}
