"""Supabase JWT 검증.

Supabase는 ES256(P-256) 비대칭 키로 access_token을 서명한다.
공개키는 `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` 에서 받아 캐시한다.

레거시 HS256(Shared secret) 프로젝트라면 SUPABASE_JWT_SECRET을 통한
fallback으로 동작한다.
"""
import os

import jwt
from jwt import PyJWKClient

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    """SUPABASE_URL이 설정돼 있으면 JWKS 클라이언트를 lazy 캐시."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        return None
    jwks_url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


def verify_supabase_jwt(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")

    # 1) ES256/RS256 — JWKS 기반
    if alg in ("ES256", "RS256"):
        client = _get_jwks_client()
        if client is None:
            raise RuntimeError(
                f"Token signed with {alg} but SUPABASE_URL is not set; "
                "set SUPABASE_URL=https://<project>.supabase.co"
            )
        signing_key = client.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token, signing_key, algorithms=[alg],
            audience="authenticated",
        )

    # 2) HS256 — 레거시 shared secret
    if alg == "HS256":
        secret = os.getenv("SUPABASE_JWT_SECRET")
        if not secret:
            raise RuntimeError(
                "Token signed with HS256 but SUPABASE_JWT_SECRET is not set"
            )
        return jwt.decode(
            token, secret, algorithms=["HS256"],
            audience="authenticated",
        )

    raise RuntimeError(f"Unsupported JWT alg: {alg}")
