"""버그 제보 관리 라우터 — backend `/internal/reports`에 그대로 위임."""
from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query

from .. import backend_client
from ..admin_auth import require_admin

router = APIRouter(tags=["reports"], dependencies=[Depends(require_admin)])


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(
        status_code=e.response.status_code,
        detail=f"backend: {e.response.text[:200]}",
    )


@router.get("/api/reports", summary="버그 제보 목록")
async def list_reports(
    status: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    try:
        return backend_client.list_reports(
            status=status, category=category, limit=limit, offset=offset
        )
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.get("/api/reports/{report_id}", summary="버그 제보 상세")
async def get_report(
    report_id: Annotated[int, PathParam()],
) -> dict[str, Any]:
    try:
        return backend_client.get_report(report_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.patch("/api/reports/{report_id}", summary="버그 제보 상태/메모 수정")
async def update_report(
    report_id: Annotated[int, PathParam()],
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return backend_client.update_report(report_id, payload)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)


@router.delete("/api/reports/{report_id}", summary="버그 제보 삭제")
async def delete_report(
    report_id: Annotated[int, PathParam()],
) -> dict[str, Any]:
    try:
        return backend_client.delete_report(report_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
