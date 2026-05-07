from fastapi import APIRouter, HTTPException

from ..schemas import TutorResponse
from ..storage import get_session
from ..storage.problems import get_problem
from ..storage.submissions import get_submission
from ..tutor import tutor as run_tutor

router = APIRouter(prefix="/tutor", tags=["tutor"])


@router.post("/{submission_id}", response_model=TutorResponse)
async def request_tutor(submission_id: int) -> TutorResponse:
    with get_session() as session:
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

    return TutorResponse(
        submission_id=submission_id,
        message=message,
    )
