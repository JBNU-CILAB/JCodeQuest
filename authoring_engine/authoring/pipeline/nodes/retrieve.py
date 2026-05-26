"""RAG exemplar 검색 노드.

같은 카테고리 approved 문제 중 "관련 있지만 서로 다른" 모범 사례를 MMR로 골라
draft 프롬프트의 grounding 자료로 넘긴다. novelty 검사가 임베딩을 "밀어내기"로
쓰는 것과 반대로, 여기선 "끌어오기"로 한 번 더 쓴다(같은 bge-m3, 같은 데이터).

설계 함정: 가장 유사한 top-k를 그대로 보여주면 모델이 베껴 중복을 만들고 자기
novelty 게이트에 걸린다. 그래서 MMR(λ)로 관련성과 다양성을 균형 잡고, 전체
statement가 아니라 IntentRubric 압축본만 넘겨 '구조만 배우고 내용은 안 베끼게' 한다.

모든 실패는 fail-open(예시 없이 생성하는 기존 동작으로 폴백) — 파이프라인을 막지 않는다.
설계 문서: docs/rag-authoring-plan.md.
"""
from __future__ import annotations

import logging

from ...backend_client import (
    fetch_category_embeddings as _fetch_embeddings,
    fetch_problem as _fetch_problem,
)
from ...config import (
    RAG_ENABLED,
    RAG_LEVEL_WINDOW,
    RAG_MIN_JUDGE_SCORE,
    RAG_MMR_LAMBDA,
    RAG_TOP_K,
)
from ...embeddings import embed_text, mmr_select, problem_text
from ...schemas import AuthoringState

log = logging.getLogger(__name__)

# bronze < silver < gold. 알 수 없는 레벨은 윈도 필터를 건너뛴다(포함).
_LEVEL_ORDER = {"bronze": 0, "silver": 1, "gold": 2}


def _within_level_window(sibling_level: str | None, target_level: str | None) -> bool:
    """sibling_level이 target_level에서 ±RAG_LEVEL_WINDOW 안이면 True.
    어느 한쪽이라도 알 수 없는 레벨이면 fail-open으로 포함한다."""
    si = _LEVEL_ORDER.get(sibling_level or "")
    ti = _LEVEL_ORDER.get(target_level or "")
    if si is None or ti is None:
        return True
    return abs(si - ti) <= RAG_LEVEL_WINDOW


def _passes_quality(judge_score: float | None) -> bool:
    """judge_score 품질 게이트. None(메타 없는 수기 원본 등)은 항상 통과시킨다."""
    if RAG_MIN_JUDGE_SCORE <= 0 or judge_score is None:
        return True
    return judge_score >= RAG_MIN_JUDGE_SCORE


def retrieve_exemplars(state: AuthoringState) -> dict:
    """원본 임베딩을 앵커로 같은 카테고리 형제 풀에서 MMR로 exemplar를 고른다.

    1. 앵커 = 원본 문제 텍스트의 임베딩(저장본 대신 재계산 — 형제 임베딩과 동일 함수라 일관).
    2. 풀 = 같은 카테고리 approved 형제(novelty가 이미 적재한 sibling_embeddings 재사용,
       없으면 직접 조회) 중 레벨 윈도 + 품질 게이트 통과 + 임베딩 보유 항목.
    3. MMR(λ)로 top-k id 선정 → 그 몇 개만 full rubric을 hydrate해 state.exemplars로.
    """
    if not RAG_ENABLED:
        return {"exemplars": []}

    original = state["original_problem"]
    if not original:
        return {"exemplars": []}

    # 1) 앵커 임베딩 — 실패하면 예시 없이 진행
    try:
        anchor = embed_text(
            problem_text(
                original.get("title", ""),
                original.get("statement", ""),
                original.get("intent_rubric", {}) or {},
            )
        )
    except Exception as exc:  # noqa: BLE001 — fail-open
        log.warning("retrieve: 앵커 임베딩 실패 — RAG fail-open: %s", exc)
        return {"exemplars": []}

    # 2) 형제 풀 확보 — novelty가 이미 적재했으면 재사용(중복 HTTP 회피), 없으면 조회
    siblings = state.get("sibling_embeddings")
    if not siblings:
        try:
            siblings = [
                e.model_dump()
                for e in _fetch_embeddings(state["original_problem_id"])
            ]
        except Exception as exc:  # noqa: BLE001 — fail-open
            log.warning("retrieve: category-embeddings 조회 실패 — RAG fail-open: %s", exc)
            return {"exemplars": []}

    target_level = original.get("level")
    pool: list[tuple[int, list[float], dict]] = []
    for e in siblings:
        emb = e.get("embedding")
        if not emb:
            continue  # 미백필 형제는 비교 불가 — 건너뜀
        if not _within_level_window(e.get("level"), target_level):
            continue
        if not _passes_quality(e.get("judge_score")):
            continue
        pool.append((e.get("id"), emb, e))

    if not pool:
        # 빈 코퍼스(신규 카테고리·미백필) → 예시 없이 생성으로 폴백
        return {"exemplars": []}

    selected = mmr_select(anchor, pool, k=RAG_TOP_K, lam=RAG_MMR_LAMBDA)

    # 3) 고른 id만 full rubric hydrate (개별 조회 실패는 건너뜀)
    exemplars: list[dict] = []
    for eid, _vec, _payload in selected:
        if eid is None:
            continue
        try:
            full = _fetch_problem(eid)
        except Exception as exc:  # noqa: BLE001 — 개별 실패는 그 항목만 스킵
            log.warning("retrieve: exemplar %s hydrate 실패 — 스킵: %s", eid, exc)
            continue
        r = full.intent_rubric
        exemplars.append(
            {
                "id": full.id,
                "title": full.title,
                "one_line_summary": r.one_line_summary,
                "expected_approach": r.expected_approach,
                "key_insight": r.key_insight,
                "expected_complexity": r.expected_complexity,
            }
        )

    log.info(
        "retrieve: 카테고리 풀 %d개 중 exemplar %d개 선정 (id=%s)",
        len(pool),
        len(exemplars),
        [e["id"] for e in exemplars],
    )
    return {"exemplars": exemplars}
