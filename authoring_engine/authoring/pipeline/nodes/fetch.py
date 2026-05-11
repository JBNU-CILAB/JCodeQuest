from ...config import ensure_backend_on_path
from ...schemas import AuthoringState


def fetch_problem(state: AuthoringState) -> dict:
    """DB에서 원본 문제와 같은 카테고리의 approved 문제(seeds)를 가져온다."""
    ensure_backend_on_path()
    from src.storage.db import get_session  # type: ignore[import]
    from src.storage.problems import get_problem, list_problems  # type: ignore[import]

    pid = state["original_problem_id"]
    with get_session() as session:
        problem = get_problem(session, pid)
        if problem is None:
            raise ValueError(f"Problem {pid} not found in DB")

        seeds_raw = list_problems(session, status="approved", category=problem.category)
        seeds = [p.model_dump() for p in seeds_raw if p.id != pid][:3]

    return {
        "original_problem": problem.model_dump(),
        "seeds": seeds,
    }
