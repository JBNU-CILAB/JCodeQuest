"""Google OAuth 로그인 라우터.

흐름:
  GET  /auth/login    → 302 Google (state/nonce는 Starlette SessionMiddleware의 임시 쿠키로)
  GET  /auth/callback → ID token 검증 + hd 검증 + get_or_create_user + 세션 발급 + 302 frontend
  POST /auth/logout   → SessionRow 삭제 + 쿠키 clear

dev stub (JCQ_AUTH_ALLOW_DEV_STUB=1일 때만 등록):
  POST /auth/dev-login?email=foo@example.com&name=Foo → 세션 발급
"""
import os
from typing import Annotated

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from ..auth.deps import SESSION_COOKIE
from ..auth.google import get_oauth
from ..storage import get_session
from ..storage.sessions import create_session, delete_session
from ..storage.users import get_or_create_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _frontend_redirect() -> str:
    return os.getenv("JCQ_FRONTEND_REDIRECT_URL", "/")


def _allowed_hd() -> str | None:
    hd = os.getenv("JCQ_AUTH_ALLOWED_HD", "jbnu.ac.kr")
    return hd or None  # 빈 문자열은 "제한 없음"으로 해석


def _ttl_days() -> int:
    return int(os.getenv("JCQ_SESSION_DAYS", "7"))


def _is_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _issue_session_cookie(response: Response, user_id: int) -> None:
    """SessionRow 생성 + 쿠키에 token set."""
    with get_session() as s:
        token, _expires_at = create_session(
            s, user_id=user_id, ttl_days=_ttl_days()
        )
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


@router.get(
    "/login",
    summary="Google OAuth 로그인 시작",
    description=(
        "Google OAuth의 authorize 엔드포인트로 302 리다이렉트한다. "
        "state/nonce는 Starlette SessionMiddleware의 임시 쿠키에 저장."
    ),
    responses={302: {"description": "Google authorize URL로 리다이렉트"}},
)
async def login(request: Request):
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI") or str(
        request.url_for("auth_callback")
    )
    return await get_oauth().google.authorize_redirect(request, redirect_uri)


@router.get(
    "/callback",
    name="auth_callback",
    summary="Google OAuth 콜백",
    description=(
        "ID 토큰 검증 → 도메인(hd) 검증 → 사용자 upsert → SessionRow 발급 → "
        "JCQ_FRONTEND_REDIRECT_URL로 302."
    ),
    responses={
        302: {"description": "프론트엔드로 리다이렉트하며 jcq_session 쿠키 발급"},
        400: {"description": "OAuth 실패 또는 ID 토큰에 sub/email 누락"},
        403: {"description": "이메일 미인증 또는 허용 도메인이 아님"},
    },
)
async def callback(request: Request):
    try:
        token = await get_oauth().google.authorize_access_token(request)
    except OAuthError as e:
        raise HTTPException(400, f"OAuth error: {e.error}") from e

    userinfo = token.get("userinfo")
    if userinfo is None:
        raise HTTPException(400, "ID token에 userinfo 없음")

    sub = userinfo.get("sub")
    email = userinfo.get("email")
    email_verified = userinfo.get("email_verified")
    name = userinfo.get("name") or email or "(이름 없음)"
    hd = userinfo.get("hd")

    if not sub or not email:
        raise HTTPException(400, "ID token에 sub/email 누락")
    if email_verified is False:
        raise HTTPException(403, "Google 이메일 미인증 계정")

    allowed = _allowed_hd()
    if allowed is not None and hd != allowed:
        # hd 누락(개인 gmail) 또는 다른 도메인 모두 거부
        raise HTTPException(403, f"허용 도메인이 아님 (요구: @{allowed})")

    with get_session() as s:
        user = get_or_create_user(
            s, provider="google", external_id=sub,
            display_name=name, email=email,
        )
        user_id = user.id
    assert user_id is not None

    response = RedirectResponse(_frontend_redirect(), status_code=302)
    _issue_session_cookie(response, user_id)
    return response


@router.post(
    "/logout",
    summary="세션 종료",
    description=(
        "현재 세션의 SessionRow를 즉시 삭제하고 jcq_session 쿠키를 clear한다. "
        "같은 토큰을 가진 다른 클라이언트도 그 시점부터 무효."
    ),
    responses={
        200: {
            "description": "로그아웃 완료 (쿠키가 없어도 200)",
            "content": {"application/json": {"example": {"status": "logged out"}}},
        }
    },
)
def logout(
    response: Response,
    jcq_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, str]:
    if jcq_session:
        with get_session() as s:
            delete_session(s, jcq_session)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged out"}


# ───────────────────────── dev stub ─────────────────────────

if _is_truthy(os.getenv("JCQ_AUTH_ALLOW_DEV_STUB")):

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
