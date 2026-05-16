from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from ..auth.deps import get_current_user
from ..schemas import TutorHistoryItem, TutorHistoryResponse, TutorResponse
from ..storage import get_session
from ..storage.models import UserRow
from ..storage.problems import get_problem
from ..storage.submissions import get_submission
from ..storage.tutor import (
    count_user_tutor_usage,
    create_tutor_message,
    latest_tutor_message,
    list_tutor_messages,
)
from ..tutor import tutor as run_tutor

router = APIRouter(prefix="/tutor", tags=["tutor"])

SubmissionIdPath = Annotated[int, Path(description="제출 ID", examples=[42])]


@router.post(
    "/{submission_id}",
    response_model=TutorResponse,
    summary="튜터 메시지 생성/조회",
    description=(
        "기본: 최신 사용자 요청 메시지가 있으면 그대로 반환 (LLM 호출 없음). "
        "`regenerate=true`이면 항상 새로 생성하고 새 행으로 저장한다. "
        "사용자의 API 키가 필요하며, 문제당 3회까지만 사용 가능하다."
    ),
    responses={
        403: {"description": "API 키가 없음"},
        404: {"description": "제출 또는 매칭된 문제 없음"},
        409: {"description": "submission.status != 'done' — 튜터링은 채점 완료 후에만"},
        429: {"description": "문제당 3회 튜터 사용 한도 초과"},
    },
)
async def request_tutor(
    submission_id: SubmissionIdPath,
    regenerate: Annotated[
        bool, Query(description="캐시 무시하고 새로 생성")
    ] = False,
    user: UserRow = Depends(get_current_user),
) -> TutorResponse:
    with get_session() as session:
        # API 키 확인
        if user.api_key_secret_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API 키를 설정해야 튜터 서비스를 사용할 수 있습니다.",
            )

        sub = get_submission(session, submission_id)
        if sub is None:
            raise HTTPException(404, f"submission {submission_id} not found")
        if sub.status != "done":
            raise HTTPException(
                409, f"submission status is '{sub.status}', tutoring requires 'done'"
            )

        problem = get_problem(session, sub.problem_id)
        if problem is None:
            raise HTTPException(
                404, f"problem {sub.problem_id} not found for submission {submission_id}"
            )

        # 사용 횟수 확인 (regenerate=True가 아닌 경우 캐시 확인 + 횟수 카운트)
        if not regenerate:
            # 최신 사용자 요청 메시지 캐시 확인
            cached = latest_tutor_message(session, submission_id)
            if cached is not None and cached.is_user_requested:
                return TutorResponse(
                    submission_id=submission_id, message=cached.message
                )

        # 사용 횟수 카운트
        usage_count = count_user_tutor_usage(
            session, user_id=user.id, problem_id=sub.problem_id
        )
        if usage_count >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="이 문제에 대한 튜터 사용 횟수(3회)를 초과했습니다.",
            )

        # 외부 API 호출 전에 세션 안에서 필요한 값을 모두 끌어옴 — 세션 밖에서는 lazy 속성 접근 불가.
        code = sub.code
        verdict = sub.final_verdict
        votes = list(sub.votes) if sub.votes else None
        test_results = list(sub.test_results) if sub.test_results else []

    message, _ = await run_tutor(
        problem=problem,
        code=code,
        verdict=verdict,
        votes=votes,
        test_results=test_results,
    )

    with get_session() as session:
        create_tutor_message(
            session, submission_id=submission_id, message=message, is_user_requested=True
        )

    return TutorResponse(submission_id=submission_id, message=message)


@router.get(
    "/{submission_id}/history",
    response_model=TutorHistoryResponse,
    summary="튜터 메시지 이력",
    description="해당 제출에 생성된 모든 튜터 메시지를 생성 시각 오름차순으로 반환. 사용자 인증 필수.",
    responses={404: {"description": "제출 없음"}},
)
async def tutor_history(
    submission_id: SubmissionIdPath,
    user: UserRow = Depends(get_current_user),
) -> TutorHistoryResponse:
    with get_session() as session:
        sub = get_submission(session, submission_id)
        if sub is None:
            raise HTTPException(404, f"submission {submission_id} not found")
        rows = list_tutor_messages(session, submission_id)
        usage_count = count_user_tutor_usage(
            session, user_id=user.id, problem_id=sub.problem_id
        )
        remaining_uses = max(0, 3 - usage_count)
        return TutorHistoryResponse(
            submission_id=submission_id,
            messages=[
                TutorHistoryItem(
                    id=r.id,  # type: ignore[arg-type]
                    message=r.message,
                    created_at=r.created_at,
                )
                for r in rows
            ],
            usage_count=usage_count,
            remaining_uses=remaining_uses,
        )
