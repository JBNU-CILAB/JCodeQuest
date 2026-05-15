"""단일 admin 토큰 기반 인증. /api/* 라우트에 dependency로 부착한다.

`JCQ_ADMIN_TOKEN` 미설정 시 503 fail-closed — 잘못 켜둔 라우트로 권한 흐름이
새지 않도록. 토큰 비교는 timing-safe `hmac.compare_digest`.

브라우저 대시보드는 별도 도메인에서 띄울 것을 가정하므로 `Authorization: Bearer`
헤더를 사용. EventSource는 헤더를 보낼 수 없으니, SSE 라우트를 대시보드에서
직접 구독할 일이 생기면 query token이나 폴리필이 필요하다.
"""
from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException


def require_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    token = os.getenv("JCQ_ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(503, "admin endpoint disabled (JCQ_ADMIN_TOKEN unset)")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    provided = authorization.split(None, 1)[1].strip()
    if not hmac.compare_digest(provided, token):
        raise HTTPException(401, "invalid token")
