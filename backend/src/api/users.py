"""타인 공개 프로필 조회 — 익명 여부에 따라 노출 범위가 달라진다.

마스킹은 전적으로 서버 측에서 한다. is_anonymous=True인 사용자는 닉네임/티어/EXP만
응답에 싣고 아바타·학년·학과·활동 통계는 아예 빼고 내려보낸다 — 프론트에서만 숨기면
응답 페이로드로 우회 노출되기 때문. 이메일/API 키 등 민감 필드는 어느 경우에도 미포함.
"""
from fastapi import APIRouter, HTTPException

from ..schemas import DailySolve, PublicProfileResponse, PublicProfileStats
from ..storage import get_session
from ..storage.leaderboard import _public_name, compute_user_rank
from ..storage.submissions import compute_user_streak, count_user_stats
from ..storage.users import get_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/{user_id}",
    response_model=PublicProfileResponse,
    summary="타인 공개 프로필 조회",
    description=(
        "다른 사용자의 공개 프로필을 반환한다. 인증 불필요. "
        "대상이 is_anonymous=True면 닉네임/티어/EXP만 노출하고 아바타·학년·학과·"
        "활동 통계는 모두 빼고 내려준다(서버 측 마스킹). 이메일/API 키 등 민감 정보는 "
        "익명 여부와 무관하게 절대 포함하지 않는다."
    ),
    responses={404: {"description": "user not found"}},
)
def get_user_public_profile(user_id: int) -> PublicProfileResponse:
    with get_session() as session:
        user = get_user(session, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")
        assert user.id is not None

        name = _public_name(
            user.display_name, user.nickname, bool(user.is_anonymous)
        )
        if user.is_anonymous:
            # 익명: 리더보드에 이미 보이는 닉네임/티어/점수 수준만. 나머지는 서버에서 차단.
            return PublicProfileResponse(
                user_id=user.id,
                display_name=name,
                tier=user.tier,
                exp=user.exp,
                is_anonymous=True,
            )

        solved, total = count_user_stats(session, user.id)
        streak = compute_user_streak(session, user.id)
        return PublicProfileResponse(
            user_id=user.id,
            display_name=name,
            tier=user.tier,
            exp=user.exp,
            is_anonymous=False,
            avatar_url=user.avatar_url,
            grade=user.grade,
            department=user.department,
            rank=compute_user_rank(session, exp=user.exp),
            stats=PublicProfileStats(
                solved=solved,
                total_submissions=total,
                current_streak=streak.current_streak,
                longest_streak=streak.longest_streak,
                daily_solves=[
                    DailySolve(date=d.isoformat(), count=c)
                    for d, c in streak.daily_solves
                ],
            ),
        )
