"""게임 컨셉의 핵심 화면 — 누적/주간 리더보드.

인증 없음(공개): 다른 사용자의 display_name과 tier, EXP만 노출하므로 본인 식별 정보는 새지 않는다.
"""
from typing import Annotated

from fastapi import APIRouter, Query

from ..schemas import LeaderboardEntry, LeaderboardPeriod, LeaderboardResponse
from ..storage import get_session
from ..storage.leaderboard import (
    list_leaderboard_all,
    list_leaderboard_by_grade,
    list_leaderboard_week,
)

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get(
    "",
    response_model=LeaderboardResponse,
    summary="리더보드 (전체 누적 / 주간)",
    description=(
        "period=all: UserRow.exp(첫 AC 시점에만 가산된 누적 EXP) 내림차순. "
        "period=week: 이번 ISO 주차에 기록된 제출의 points_awarded 합산. "
        "동점은 user_id 오름차순으로 안정 정렬."
    ),
)
def get_leaderboard(
    period: Annotated[
        LeaderboardPeriod,
        Query(description="all=누적 EXP, week=이번 ISO 주차 획득 점수"),
    ] = "all",
    limit: Annotated[
        int, Query(ge=1, le=100, description="상위 N (1–100)")
    ] = 50,
) -> LeaderboardResponse:
    with get_session() as session:
        if period == "all":
            rows = list_leaderboard_all(session, limit=limit)
            week_label: str | None = None
        else:
            week_label, rows = list_leaderboard_week(session, limit=limit)

    entries = [
        LeaderboardEntry(
            rank=i + 1,
            user_id=uid,
            display_name=name,
            tier=tier,
            points=points,
            avatar_url=avatar_url,
        )
        for i, (uid, name, tier, points, avatar_url) in enumerate(rows)
    ]
    return LeaderboardResponse(period=period, week=week_label, entries=entries)


@router.get(
    "/by-grade",
    response_model=LeaderboardResponse,
    summary="리더보드 (학년별 누적)",
    description=(
        "특정 학년(1~4)에 속한 사용자만 골라 누적 EXP 내림차순으로 반환. "
        "UserRow.grade가 NULL(프로필 미설정)인 사용자는 제외. "
        "응답 schema는 /leaderboard 와 동일하며 period='all', week=null 로 고정."
    ),
)
def get_leaderboard_by_grade(
    grade: Annotated[
        int, Query(ge=1, le=4, description="대상 학년 (1~4)")
    ],
    limit: Annotated[
        int, Query(ge=1, le=100, description="상위 N (1–100)")
    ] = 50,
) -> LeaderboardResponse:
    with get_session() as session:
        rows = list_leaderboard_by_grade(session, grade=grade, limit=limit)

    entries = [
        LeaderboardEntry(
            rank=i + 1,
            user_id=uid,
            display_name=name,
            tier=tier,
            points=points,
            avatar_url=avatar_url,
        )
        for i, (uid, name, tier, points, avatar_url) in enumerate(rows)
    ]
    return LeaderboardResponse(period="all", week=None, entries=entries)
