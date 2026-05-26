import logging

from ...backend_client import (
    fetch_category_embeddings as _fetch_embeddings,
    fetch_problem as _fetch,
    fetch_seeds as _fetch_seeds,
)
from ...config import NOVELTY_ENABLED
from ...schemas import AuthoringState

log = logging.getLogger(__name__)


def fetch_problem(state: AuthoringState) -> dict:
    """backend /internal API에서 원본 문제와 같은 카테고리의 approved 시드를 가져온다.

    backend가 이미 카테고리로 필터링하지만, 다른 카테고리 시드가 흘러들어오면
    변형 다양성 시그널이 오염되므로 여기서도 한 번 더 카테고리 불일치 시드를 거른다.

    신규성 검사가 켜져 있으면 같은 카테고리 approved 형제의 임베딩 전체도 함께 적재해
    generate 단계가 후보를 모든 형제와 비교할 수 있게 한다. 임베딩 조회 실패는
    fail-open(빈 모집단 → 검사 통과)으로 흡수한다.
    """
    pid = state["original_problem_id"]
    problem = _fetch(pid)
    seeds = _fetch_seeds(pid, limit=3)
    original_category = problem.category
    filtered_seeds = [s for s in seeds if s.category == original_category]

    sibling_embeddings: list[dict] = []
    if NOVELTY_ENABLED:
        try:
            sibling_embeddings = [e.model_dump() for e in _fetch_embeddings(pid)]
        except Exception as exc:  # noqa: BLE001 — fail-open: 검사 없이 진행
            log.warning("category-embeddings 조회 실패 — 신규성 검사 fail-open: %s", exc)

    return {
        "original_problem": problem.model_dump(),
        "seeds": [s.model_dump() for s in filtered_seeds],
        "sibling_embeddings": sibling_embeddings,
    }
