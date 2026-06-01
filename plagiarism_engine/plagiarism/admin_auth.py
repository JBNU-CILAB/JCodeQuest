"""단일 admin 토큰 인증 — /api/* 라우트 dependency. (authoring_engine과 동일 패턴)

`JCQ_ADMIN_TOKEN` 미설정 시 503 fail-closed. 토큰 비교는 timing-safe.
"""
from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException


def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    token = os.getenv("JCQ_ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(503, "admin endpoint disabled (JCQ_ADMIN_TOKEN unset)")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    provided = authorization.split(None, 1)[1].strip()
    if not hmac.compare_digest(provided, token):
        raise HTTPException(401, "invalid token")
