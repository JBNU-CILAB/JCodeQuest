"""공지 관리 라우터 — backend `/internal/notices`에 그대로 위임."""
from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query

from .. import backend_client
from ..admin_auth import require_admin

router = APIRouter(tags=["notices"], dependencies=[Depends(require_admin)])


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(
        status_code=e.response.status_code,
        detail=f"backend: {e.response.text[:200]}",
    )


@router.get("/api/notices", summary="공지 목록")
async def list_notices(
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict[str, Any]]:
    try:
        return backend_client.list_notices(limit=limit)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.post("/api/notices", summary="공지 등록")
async def create_notice(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return backend_client.create_notice(payload)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.patch("/api/notices/{notice_id}", summary="공지 수정")
async def update_notice(
    notice_id: Annotated[int, PathParam()],
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return backend_client.update_notice(notice_id, payload)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.delete("/api/notices/{notice_id}", summary="공지 삭제")
async def delete_notice(
    notice_id: Annotated[int, PathParam()],
) -> dict[str, Any]:
    try:
        return backend_client.delete_notice(notice_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
