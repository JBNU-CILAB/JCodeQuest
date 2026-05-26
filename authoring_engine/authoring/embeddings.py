"""신규성(중복) 검사용 임베딩 유틸.

출제 엔진은 Ollama를 이미 ChatOllama로 쓰므로 임베딩도 같은 OLLAMA_BASE_URL의
임베딩 모델(기본 bge-m3 — 한국어 statement에 적합)을 쓴다. pgvector를 쓰지 않고
backend가 JSON으로 저장한 벡터를 받아 여기서 순수 Python 코사인으로 비교한다.
문제 규모(카테고리당 수십~수백)에선 ANN 인덱스 없이 충분하다.
"""
from __future__ import annotations

import math

from langchain_ollama import OllamaEmbeddings

from .config import EMBED_MODEL, OLLAMA_BASE_URL

_embedder: OllamaEmbeddings | None = None


def _get_embedder() -> OllamaEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    return _embedder


def problem_text(title: str, statement: str, rubric: dict) -> str:
    """임베딩에 넣을 정규화 텍스트. 제목·서술에 더해 rubric의 풀이 흐름/핵심 통찰을
    포함해 '겉모습(시나리오)'이 아니라 '풀이 구조'의 유사도를 잡도록 한다.
    저장·검색·백필 모두 이 동일 함수를 써서 임베딩 일관성을 보장한다."""
    return "\n".join(
        [
            title or "",
            statement or "",
            rubric.get("expected_approach", "") or "",
            rubric.get("key_insight", "") or "",
        ]
    ).strip()


def embed_text(text: str) -> list[float]:
    """단일 텍스트 임베딩. 실패는 호출 측이 fail-open으로 흡수한다."""
    return _get_embedder().embed_query(text)


def cosine(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도. 한쪽이 비었거나 노름이 0이면 0.0."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def max_similarity(
    embedding: list[float],
    population: list[tuple[int, str, list[float] | None]],
) -> tuple[float, int | None, str]:
    """embedding과 모집단(각 (id, title, vector)) 사이 최대 코사인 유사도와
    가장 가까운 문제의 (score, id, title)을 반환. vector가 None인 항목은 건너뛴다
    (백필 전 문제 → fail-open). 비교 대상이 없으면 (0.0, None, "")."""
    best_score = 0.0
    best_id: int | None = None
    best_title = ""
    for pid, title, vec in population:
        if not vec:
            continue
        s = cosine(embedding, vec)
        if s > best_score:
            best_score, best_id, best_title = s, pid, title
    return best_score, best_id, best_title


def mmr_select(
    query_vec: list[float],
    pool: list[tuple[int, list[float], dict]],
    k: int = 3,
    lam: float = 0.5,
) -> list[tuple[int, list[float], dict]]:
    """Maximal Marginal Relevance로 pool에서 최대 k개를 고른다.

    novelty 검사와 반대 방향의 retrieval에 쓴다 — 가장 유사한 top-k를 뽑으면 모델이
    그걸 베껴 중복을 만들고 자기 자신의 novelty 게이트에 걸리므로, 관련성(query와의
    유사도)과 다양성(이미 고른 것들과의 비유사도)을 lam으로 균형 잡아 "관련 있지만
    서로 다른" 모범 사례를 고른다.

    pool 항목은 (id, vector, payload). vector가 비었으면 건너뛴다(fail-open).
    lam=0.7 → 관련성 우선, lam=0.3 → 다양성 우선. 출제엔 0.4~0.5 권장.
    """
    rest = [item for item in pool if item[1]]
    selected: list[tuple[int, list[float], dict]] = []
    while rest and len(selected) < k:
        best = None
        best_score = float("-inf")
        for item in rest:
            rel = cosine(query_vec, item[1])
            div = max((cosine(item[1], s[1]) for s in selected), default=0.0)
            score = lam * rel - (1.0 - lam) * div
            if score > best_score:
                best, best_score = item, score
        assert best is not None  # rest가 비어 있지 않으므로 항상 채워진다
        selected.append(best)
        rest.remove(best)
    return selected
