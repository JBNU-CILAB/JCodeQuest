"""공지 공개 조회 라우터. 인증 없음 — 누구나 GET 가능.

쓰기/삭제는 admin 전용으로, authoring_engine 경유 `/internal/notices`를 사용한다.
"""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from ..schemas import Notice
from ..storage import get_session
from ..storage.models import NoticeRow
from ..storage.notices import get_notice, list_notices

router = APIRouter(prefix="/notices", tags=["notices"])


def _to_notice(row: NoticeRow) -> Notice:
    assert row.id is not None
    return Notice(
        id=row.id,
        title=row.title,
        body=row.body,
        pinned=row.pinned,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "",
    response_model=list[Notice],
    summary="공지 목록",
    description="pinned 우선, created_at 내림차순. 최대 50건.",
)
def list_public_notices(
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
) -> list[Notice]:
    with get_session() as session:
        return [_to_notice(r) for r in list_notices(session, limit=limit)]


@router.get(
    "/{notice_id}",
    response_model=Notice,
    summary="공지 단건 조회",
    responses={404: {"description": "공지 없음"}},
)
def get_public_notice(
    notice_id: Annotated[int, Path(description="공지 ID")],
) -> Notice:
    with get_session() as session:
        row = get_notice(session, notice_id)
        if row is None:
            raise HTTPException(404, f"notice {notice_id} not found")
        return _to_notice(row)
