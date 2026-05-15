"""유저 관리 라우터 — backend /internal/users 위임.

엔드포인트:
  GET    /api/users                  유저 목록 (검색 + 페이지네이션)
  DELETE /api/users/{id}             유저 + 제출/튜터/세션 cascade 삭제
  DELETE /api/users/{id}/api-key     API 키만 강제 제거 (유저는 보존)
"""
from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from jcq_shared.schemas import AdminUserSummary, UserDeleteResponse

from .. import backend_client
from ..admin_auth import require_admin

router = APIRouter(tags=["users"], dependencies=[Depends(require_admin)])


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(
        status_code=e.response.status_code,
        detail=f"backend: {e.response.text[:200]}",
    )


@router.get(
    "/api/users",
    response_model=list[AdminUserSummary],
    summary="유저 목록 (검색 + 페이지네이션)",
)
async def list_users(
    search: Annotated[str | None, Query(description="display_name/email/nickname 부분 일치")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminUserSummary]:
    try:
        return backend_client.list_users(search=search, limit=limit, offset=offset)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.delete(
    "/api/users/{user_id}",
    response_model=UserDeleteResponse,
    summary="유저 + 제출/튜터/세션 cascade 삭제 (하드)",
    responses={404: {"description": "유저 없음"}},
)
async def delete_user(
    user_id: Annotated[int, PathParam(description="삭제할 유저 ID")],
) -> UserDeleteResponse:
    try:
        return backend_client.delete_user(user_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.delete(
    "/api/users/{user_id}/api-key",
    summary="유저 API 키 강제 제거 (vault row 포함)",
    responses={404: {"description": "유저 없음"}},
)
async def force_clear_api_key(
    user_id: Annotated[int, PathParam()],
) -> dict:
    try:
        return backend_client.clear_user_api_key(user_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
