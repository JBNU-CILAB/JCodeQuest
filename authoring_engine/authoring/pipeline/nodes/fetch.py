from ...backend_client import fetch_problem as _fetch, fetch_seeds as _fetch_seeds
from ...schemas import AuthoringState


def fetch_problem(state: AuthoringState) -> dict:
    """backend /internal API에서 원본 문제와 같은 카테고리의 approved 시드를 가져온다."""
    pid = state["original_problem_id"]
    problem = _fetch(pid)
    seeds = _fetch_seeds(pid, limit=3)
    return {
        "original_problem": problem.model_dump(),
        "seeds": [s.model_dump() for s in seeds],
    }
