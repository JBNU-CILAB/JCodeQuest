"""인증된 본인 프로필 + 본인 제출 이력."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth.deps import get_current_user
from ..schemas import (
    ApiKeyUpdateRequest,
    ApiKeyUpdateResponse,
    DailySolve,
    EnsembleVerdict,
    MeResponse,
    ProfileUpdateRequest,
    StreakResponse,
    SubmissionListItem,
    SubmissionListResponse,
)
from ..storage import get_session
from ..storage.models import UserRow
from ..storage.submissions import compute_user_streak, list_user_submissions
from ..storage.users import set_user_api_key, update_user_profile

router = APIRouter(prefix="/me", tags=["me"])


def _to_me_response(user: UserRow) -> MeResponse:
    return MeResponse(
        id=user.id,  # type: ignore[arg-type]
        display_name=user.display_name,
        email=user.email,
        provider=user.provider,  # type: ignore[arg-type]
        exp=user.exp,
        tier=user.tier,
        has_api_key=bool(user.api_key_secret_id),
        nickname=user.nickname,
        grade=user.grade,
        department=user.department,
        is_anonymous=bool(user.is_anonymous),
        avatar_url=user.avatar_url,
    )


@router.get(
    "",
    response_model=MeResponse,
    summary="내 프로필 조회",
    description="현재 세션의 사용자 프로필을 반환한다.",
    responses={401: {"description": "유효한 세션 쿠키 없음"}},
)
def me(user: UserRow = Depends(get_current_user)) -> MeResponse:
    return _to_me_response(user)


@router.patch(
    "",
    response_model=MeResponse,
    summary="내 프로필 수정 (학년/학과/닉네임)",
    description=(
        "학년, 학과, 닉네임을 부분 갱신한다. 본문에서 생략한 필드는 미변경, "
        "null을 명시하면 해당 필드를 비운다."
    ),
    responses={
        401: {"description": "유효한 세션 쿠키/토큰 없음"},
        404: {"description": "user not found"},
    },
)
def update_my_profile(
    payload: ProfileUpdateRequest,
    user: UserRow = Depends(get_current_user),
) -> MeResponse:
    assert user.id is not None
    # exclude_unset: 본문에서 생략된 필드는 dict에 없음 → 그 필드는 미변경.
    # null로 명시된 필드는 None 값으로 들어옴 → 해당 컬럼을 비운다.
    fields = payload.model_dump(exclude_unset=True)
    if isinstance(fields.get("nickname"), str):
        fields["nickname"] = fields["nickname"].strip() or None
    if isinstance(fields.get("department"), str):
        fields["department"] = fields["department"].strip() or None
    if isinstance(fields.get("avatar_url"), str):
        fields["avatar_url"] = fields["avatar_url"].strip() or None
    # is_anonymous는 명시적 true/false만 의미가 있다 — null이면 미변경 신호로 처리.
    if fields.get("is_anonymous") is None:
        fields.pop("is_anonymous", None)
    with get_session() as session:
        updated = update_user_profile(session, user.id, **fields)
        if updated is None:
            raise HTTPException(status_code=404, detail="user not found")
    return _to_me_response(updated)


@router.put(
    "/api-key",
    response_model=ApiKeyUpdateResponse,
    summary="내 학내 GPT API 키 등록/갱신",
    description=(
        "현재 사용자의 학내 GPT(gpt.jbnu.ai) API 키를 저장한다. "
        "키 값은 응답에 포함되지 않는다."
    ),
    responses={401: {"description": "유효한 세션 쿠키/토큰 없음"}},
)
def update_my_api_key(
    payload: ApiKeyUpdateRequest,
    user: UserRow = Depends(get_current_user),
) -> ApiKeyUpdateResponse:
    assert user.id is not None
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=422, detail="api_key가 비어 있다")
    with get_session() as session:
        updated = set_user_api_key(session, user.id, api_key=api_key)
        if updated is None:
            raise HTTPException(status_code=404, detail="user not found")
    return ApiKeyUpdateResponse(has_api_key=True)


def _to_submission_item(row) -> SubmissionListItem:
    return SubmissionListItem(
        id=row.id,
        problem_id=row.problem_id,
        status=row.status,
        final_verdict=row.final_verdict,
        mode=row.mode,
        points_awarded=row.points_awarded,
        max_elapsed_ms=row.max_elapsed_ms,
        peak_memory_kb=row.peak_memory_kb,
        created_at=row.created_at,
    )


@router.get(
    "/submissions",
    response_model=SubmissionListResponse,
    summary="내 제출 목록",
    description=(
        "본인이 낸 제출들을 최신순으로 반환한다. "
        "`code` 필드는 페이로드 비대해서 제외 — 상세는 `GET /grade/{id}`."
    ),
    responses={401: {"description": "유효한 세션 쿠키 없음"}},
)
def list_my_submissions(
    problem_id: Annotated[
        int | None, Query(description="특정 문제로 필터")
    ] = None,
    verdict: Annotated[
        EnsembleVerdict | None,
        Query(
            description=(
                "AC | SUS. sandbox-fail은 final_verdict=SUS로 들어가므로 "
                "verdict=SUS에 포함된다."
            )
        ),
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="페이지 크기 (1–100)")
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="오프셋")] = 0,
    user: UserRow = Depends(get_current_user),
) -> SubmissionListResponse:
    assert user.id is not None
    with get_session() as session:
        rows, total = list_user_submissions(
            session,
            user.id,
            problem_id=problem_id,
            verdict=verdict,
            limit=limit,
            offset=offset,
        )
        items = [_to_submission_item(r) for r in rows]
    return SubmissionListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


@router.get(
    "/streak",
    response_model=StreakResponse,
    summary="내 풀이 스트릭",
    description=(
        "'새 문제를 처음 AC한 날' 기준 연속 일수를 반환한다. "
        "날짜 경계는 KST(UTC+9). 오늘 또는 어제까지 이어진 풀이가 있어야 current가 유지된다."
    ),
    responses={401: {"description": "유효한 세션 쿠키/토큰 없음"}},
)
def get_my_streak(user: UserRow = Depends(get_current_user)) -> StreakResponse:
    assert user.id is not None
    with get_session() as session:
        stats = compute_user_streak(session, user.id)
    return StreakResponse(
        current_streak=stats.current_streak,
        longest_streak=stats.longest_streak,
        last_solved_date=stats.last_solved_date.isoformat() if stats.last_solved_date else None,
        daily_solves=[
            DailySolve(date=d.isoformat(), count=c) for d, c in stats.daily_solves
        ],
    )
