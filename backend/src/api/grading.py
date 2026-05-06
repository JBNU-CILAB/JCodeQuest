import os

from fastapi import APIRouter, HTTPException

from ..judge.ensemble import vote
from ..schemas import GradeRequest, GradeResponse
from ..storage import get_session
from ..storage.problems import get_problem
from ..storage.submissions import (
    MAX_ATTEMPTS,
    attempt_status,
    create_submission,
    save_grading,
)

router = APIRouter(prefix="/grade", tags=["grading"])


@router.post("", response_model=GradeResponse)
async def grade(req: GradeRequest) -> GradeResponse:
    base_url = os.getenv("OLLAMA_BASE_URL")

    with get_session() as session:
        problem = get_problem(session, req.problem_id)
        if problem is None:
            raise HTTPException(404, f"problem {req.problem_id} not found")

        status = attempt_status(session, req.user_id, req.problem_id)
        if status.solved:
            raise HTTPException(409, "이미 해결한 문제입니다")
        if status.attempts >= MAX_ATTEMPTS:
            raise HTTPException(
                429, f"최대 제출 횟수({MAX_ATTEMPTS}회) 초과"
            )

        submission_id = create_submission(
            session,
            user_id=req.user_id,
            problem_id=req.problem_id,
            code=req.code,
        )

    ensemble = await vote(problem, req.code, req.test_results, base_url=base_url)
    points = problem.points if ensemble.final_verdict == "AC" else 0

    with get_session() as session:
        save_grading(
            session, submission_id, ensemble, points_on_ac=problem.points
        )

    return GradeResponse(
        submission_id=submission_id,
        ensemble=ensemble,
        points_awarded=points,
    )
