from fastapi import APIRouter, HTTPException

from ..schemas import TutorHistoryItem, TutorHistoryResponse, TutorResponse
from ..storage import get_session
from ..storage.problems import get_problem
from ..storage.submissions import get_submission
from ..storage.tutor import (
    create_tutor_message,
    latest_tutor_message,
    list_tutor_messages,
)
from ..tutor import tutor as run_tutor

router = APIRouter(prefix="/tutor", tags=["tutor"])


@router.post("/{submission_id}", response_model=TutorResponse)
async def request_tutor(
    submission_id: int, regenerate: bool = False
) -> TutorResponse:
    """튜터 메시지 생성/조회.
    - 기본: 최신 캐시가 있으면 그대로 반환 (LLM 호출 없음)
    - `?regenerate=true`: 항상 새로 생성 + 새 행으로 저장
    """
    with get_session() as session:
        sub = get_submission(session, submission_id)
        if sub is None:
            raise HTTPException(404, f"submission {submission_id} not found")
        if sub.status != "done":
            raise HTTPException(
                409, f"submission status is '{sub.status}', tutoring requires 'done'"
            )

        if not regenerate:
            cached = latest_tutor_message(session, submission_id)
            if cached is not None:
                return TutorResponse(
                    submission_id=submission_id, message=cached.message
                )

        problem = get_problem(session, sub.problem_id)
        if problem is None:
            raise HTTPException(
                404, f"problem {sub.problem_id} not found for submission {submission_id}"
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
            session, submission_id=submission_id, message=message
        )

    return TutorResponse(submission_id=submission_id, message=message)


@router.get("/{submission_id}/history", response_model=TutorHistoryResponse)
async def tutor_history(submission_id: int) -> TutorHistoryResponse:
    with get_session() as session:
        sub = get_submission(session, submission_id)
        if sub is None:
            raise HTTPException(404, f"submission {submission_id} not found")
        rows = list_tutor_messages(session, submission_id)
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
        )
