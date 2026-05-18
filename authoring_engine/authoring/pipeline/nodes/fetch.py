from ...backend_client import fetch_problem as _fetch, fetch_seeds as _fetch_seeds
from ...schemas import AuthoringState


def fetch_problem(state: AuthoringState) -> dict:
    """backend /internal API에서 원본 문제와 같은 카테고리의 approved 시드를 가져온다.

    backend가 이미 카테고리로 필터링하지만, 다른 카테고리 시드가 흘러들어오면
    변형 다양성 시그널이 오염되므로 여기서도 한 번 더 카테고리 불일치 시드를 거른다.
    """
    pid = state["original_problem_id"]
    problem = _fetch(pid)
    seeds = _fetch_seeds(pid, limit=3)
    original_category = problem.category
    filtered_seeds = [s for s in seeds if s.category == original_category]
    return {
        "original_problem": problem.model_dump(),
        "seeds": [s.model_dump() for s in filtered_seeds],
    }
