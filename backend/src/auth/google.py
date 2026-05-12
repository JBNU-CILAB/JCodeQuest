"""Google OIDC 클라이언트. authlib에 discovery URL 등록 한 번."""
import os

from authlib.integrations.starlette_client import OAuth

_GOOGLE_DISCOVERY = (
    "https://accounts.google.com/.well-known/openid-configuration"
)

_oauth: OAuth | None = None


def get_oauth() -> OAuth:
    """모듈 로드 시 즉시 생성하면 GOOGLE_CLIENT_ID 미설정 환경(테스트 import만 하는 경우)에서 깨짐.
    첫 호출 때 lazy 생성."""
    global _oauth
    if _oauth is not None:
        return _oauth

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set"
        )

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=_GOOGLE_DISCOVERY,
        client_kwargs={"scope": "openid email profile"},
    )
    _oauth = oauth
    return oauth
