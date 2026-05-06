import os

from fastapi import APIRouter, HTTPException

from ..llm.ensemble import vote
from ..schemas import GradeRequest, GradeResponse
from ..storage import get_session
from ..storage.problems import get_problem
from ..storage.submissions import create_submission, save_grading

router = APIRouter(prefix="/grade", tags=["grading"])


@router.post("", response_model=GradeResponse)
async def grade(req: GradeRequest) -> GradeResponse:
    base_url = os.getenv("OLLAMA_BASE_URL")

    with get_session() as session:
        problem = get_problem(session, req.problem_id)
        if problem is None:
            raise HTTPException(404, f"problem {req.problem_id} not found")
        submission_id = create_submission(
            session,
            user_id=req.user_id,
            problem_id=req.problem_id,
            code=req.code,
        )

    ensemble = await vote(problem, req.code, req.test_results, base_url=base_url)

    with get_session() as session:
        save_grading(session, submission_id, ensemble)

    return GradeResponse(submission_id=submission_id, ensemble=ensemble)
