"""RAG exemplar 검색 단위 테스트 — docs/rag-authoring-plan.md §8.1.

- mmr_select: 관련성/다양성 균형, k 제한, 빈 벡터 스킵.
- retrieve_exemplars: 레벨 윈도/품질 게이트 필터, hydrate, fail-open(빈 코퍼스·
  앙커 실패·RAG 비활성), sibling_embeddings 재사용 vs 직접 조회.

LLM/HTTP 호출은 retrieve 모듈에 import된 이름(embed_text, _fetch_embeddings,
_fetch_problem)을 monkeypatch한다 — 정의 모듈이 아니라 호출 모듈 패치 규칙(docs/testing.md).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from authoring.embeddings import mmr_select
from authoring.pipeline.nodes import retrieve as R


# ── mmr_select ───────────────────────────────────────────────────────────────
def test_mmr_first_pick_is_most_relevant():
    query = [1.0, 0.0]
    pool = [
        (1, [1.0, 0.0], {}),   # query와 동일 → 가장 관련성 높음
        (2, [0.0, 1.0], {}),   # 직교
        (3, [0.7, 0.7], {}),
    ]
    out = mmr_select(query, pool, k=1, lam=0.7)
    assert [pid for pid, _, _ in out] == [1]


def test_mmr_second_pick_favors_diversity():
    """다양성 우선(λ=0.3)이면 첫 픽과 거의 같은 후보 대신 다른 후보를 골라야 한다."""
    query = [1.0, 0.0]
    pool = [
        (1, [0.90, 0.10], {}),   # 가장 관련성 높음 → 먼저 선택됨
        (2, [0.88, 0.12], {}),   # 1과 거의 동일 → 다양성 페널티
        (3, [0.0, 1.0], {}),     # 직교 → 다양성 보너스
    ]
    out = mmr_select(query, pool, k=2, lam=0.3)
    picked = [pid for pid, _, _ in out]
    assert picked[0] == 1
    assert picked[1] == 3  # 중복(2)이 아니라 다양한 3을 골라야 함


def test_mmr_respects_k_and_skips_empty_vectors():
    query = [1.0, 0.0]
    pool = [
        (1, [1.0, 0.0], {}),
        (2, [], {}),            # 빈 벡터 → 스킵
        (3, [0.0, 1.0], {}),
        (4, [0.5, 0.5], {}),
    ]
    out = mmr_select(query, pool, k=2, lam=0.5)
    ids = [pid for pid, _, _ in out]
    assert len(out) == 2
    assert 2 not in ids  # 빈 벡터는 절대 선택되지 않음


def test_mmr_empty_pool_returns_empty():
    assert mmr_select([1.0, 0.0], [], k=3) == []


# ── retrieve_exemplars ───────────────────────────────────────────────────────
def _rubric(summary="요약", approach="접근", insight="통찰", complexity="O(n)"):
    return SimpleNamespace(
        one_line_summary=summary,
        expected_approach=approach,
        key_insight=insight,
        expected_complexity=complexity,
    )


def _fake_problem(pid, title="제목"):
    return SimpleNamespace(id=pid, title=title, intent_rubric=_rubric())


def _state(level="silver", siblings=None):
    return {
        "original_problem_id": 1,
        "original_problem": {
            "title": "원본",
            "statement": "원본 본문",
            "level": level,
            "intent_rubric": {"expected_approach": "x", "key_insight": "y"},
        },
        "sibling_embeddings": siblings if siblings is not None else [],
    }


@pytest.fixture
def patch_rag(monkeypatch):
    """RAG 기본 활성 + 결정론적 임베딩/조회로 고정. 개별 테스트가 세부를 덮어쓴다."""
    monkeypatch.setattr(R, "RAG_ENABLED", True)
    monkeypatch.setattr(R, "RAG_TOP_K", 3)
    monkeypatch.setattr(R, "RAG_MMR_LAMBDA", 0.5)
    monkeypatch.setattr(R, "RAG_LEVEL_WINDOW", 1)
    monkeypatch.setattr(R, "RAG_MIN_JUDGE_SCORE", 0.0)
    monkeypatch.setattr(R, "embed_text", lambda text: [1.0, 0.0])
    monkeypatch.setattr(
        R, "_fetch_problem", lambda pid: _fake_problem(pid, f"형제{pid}")
    )
    return monkeypatch


def test_retrieve_disabled_returns_empty(patch_rag):
    patch_rag.setattr(R, "RAG_ENABLED", False)
    assert R.retrieve_exemplars(_state()) == {"exemplars": []}


def test_retrieve_happy_path_hydrates_rubric(patch_rag):
    siblings = [
        {"id": 10, "title": "형제10", "embedding": [1.0, 0.0], "level": "silver", "judge_score": 0.9},
        {"id": 11, "title": "형제11", "embedding": [0.0, 1.0], "level": "silver", "judge_score": 0.8},
    ]
    out = R.retrieve_exemplars(_state(siblings=siblings))
    ex = out["exemplars"]
    assert {e["id"] for e in ex} == {10, 11}
    # rubric 압축본 필드가 hydrate됨
    assert set(ex[0]) == {
        "id", "title", "one_line_summary",
        "expected_approach", "key_insight", "expected_complexity",
    }


def test_retrieve_filters_out_of_level_window(patch_rag):
    # 목표 bronze, 윈도 1 → gold(거리 2)는 제외, silver(거리 1)는 포함
    siblings = [
        {"id": 10, "title": "s", "embedding": [1.0, 0.0], "level": "silver", "judge_score": None},
        {"id": 11, "title": "g", "embedding": [0.0, 1.0], "level": "gold", "judge_score": None},
    ]
    out = R.retrieve_exemplars(_state(level="bronze", siblings=siblings))
    assert {e["id"] for e in out["exemplars"]} == {10}


def test_retrieve_quality_gate_excludes_low_score_keeps_none(patch_rag):
    patch_rag.setattr(R, "RAG_MIN_JUDGE_SCORE", 0.7)
    siblings = [
        {"id": 10, "title": "low", "embedding": [1.0, 0.0], "level": "silver", "judge_score": 0.5},
        {"id": 11, "title": "ok", "embedding": [0.0, 1.0], "level": "silver", "judge_score": 0.9},
        {"id": 12, "title": "manual", "embedding": [0.5, 0.5], "level": "silver", "judge_score": None},
    ]
    out = R.retrieve_exemplars(_state(siblings=siblings))
    ids = {e["id"] for e in out["exemplars"]}
    assert 10 not in ids       # 0.5 < 0.7 → 제외
    assert ids == {11, 12}     # 0.9 통과, None(수기 원본) 통과


def test_retrieve_empty_corpus_fail_open(patch_rag):
    # 임베딩 미백필 형제만 → 풀이 비어 예시 없이 폴백
    siblings = [{"id": 10, "title": "s", "embedding": None, "level": "silver", "judge_score": 0.9}]
    assert R.retrieve_exemplars(_state(siblings=siblings)) == {"exemplars": []}


def test_retrieve_anchor_embed_failure_fail_open(patch_rag):
    def boom(_text):
        raise RuntimeError("ollama down")

    patch_rag.setattr(R, "embed_text", boom)
    siblings = [{"id": 10, "title": "s", "embedding": [1.0, 0.0], "level": "silver", "judge_score": 0.9}]
    assert R.retrieve_exemplars(_state(siblings=siblings)) == {"exemplars": []}


def test_retrieve_fetches_when_siblings_absent(patch_rag):
    """state에 sibling_embeddings가 없으면 backend에서 직접 조회한다(novelty off 경로)."""
    fetched = [
        SimpleNamespace(
            model_dump=lambda: {"id": 20, "title": "f", "embedding": [1.0, 0.0],
                                "level": "silver", "judge_score": 0.9}
        )
    ]
    patch_rag.setattr(R, "_fetch_embeddings", lambda pid: fetched)
    state = _state()
    del state["sibling_embeddings"]  # novelty 비활성 → fetch가 적재하지 않은 상태
    out = R.retrieve_exemplars(state)
    assert {e["id"] for e in out["exemplars"]} == {20}


def test_retrieve_top_k_caps_selection(patch_rag):
    patch_rag.setattr(R, "RAG_TOP_K", 2)
    siblings = [
        {"id": i, "title": f"s{i}", "embedding": [1.0, 0.0], "level": "silver", "judge_score": 0.9}
        for i in range(10, 15)
    ]
    out = R.retrieve_exemplars(_state(siblings=siblings))
    assert len(out["exemplars"]) == 2
