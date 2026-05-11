from fastapi import APIRouter, HTTPException

from ..schemas import Problem
from ..storage import get_session
from ..storage.problems import get_problem, list_problems

router = APIRouter(prefix="/problems", tags=["problems"])


@router.get("", response_model=list[Problem])
def get_problems(status: str = "approved") -> list[Problem]:
    with get_session() as session:
        return list_problems(session, status=status)


@router.get("/{problem_id}", response_model=Problem)
def get_problem_by_id(problem_id: int) -> Problem:
    with get_session() as session:
        problem = get_problem(session, problem_id)
        if problem is None:
            raise HTTPException(404, f"problem {problem_id} not found")
        return problem
