"""신규성 검사 지원 엔드포인트/저장 계층.

- GET  /internal/problems/{id}/category-embeddings — 카테고리 형제 임베딩(자기 제외, NULL 포함)
- PATCH /internal/problems/{id}/embedding          — 백필/갱신
- POST /internal/problems                           — embedding 동봉 저장
- 인증(Bearer JCQ_INTERNAL_SECRET) 가드 / 404
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from src.schemas import IntentRubric, Problem, TestCase
from src.storage import get_session
from src.storage.models import ProblemRow
from src.storage.problems import (
    create_problem,
    list_category_embeddings,
    set_problem_embedding,
)


@pytest.fixture(autouse=True)
def _internal_secret(monkeypatch):
    monkeypatch.setenv("JCQ_INTERNAL_SECRET", "test-internal-secret")


@pytest.fixture
def client():
    from src.main import app

    with TestClient(app) as c:
        yield c


def _auth():
    return {"Authorization": f"Bearer {os.environ['JCQ_INTERNAL_SECRET']}"}


def _problem(title: str, category: str) -> Problem:
    return Problem(
        id=0,
        title=title,
        statement=f"{title} 본문",
        category=category,
        level="bronze",
        points=100,
        time_limit_ms=2000,
        memory_limit_mb=256,
        reference_code="print(1)\n",
        intent_rubric=IntentRubric(
            expected_approach="흐름",
            expected_complexity="O(n)",
            must_handle=["a"],
            forbidden_patterns=["b"],
            key_insight="통찰",
            one_line_summary="요약",
        ),
        test_cases=[TestCase(ordinal=1, stdin="1\n", expected_stdout="1", is_sample=True)],
    )


# ── storage 계층 ───────────────────────────────────────────────────────────
def test_create_problem_persists_embedding():
    with get_session() as s:
        pid = create_problem(s, _problem("임베딩저장", "math"), status="approved",
                             embedding=[0.1, 0.2, 0.3])
        row = s.get(ProblemRow, pid)
        assert row.embedding == [0.1, 0.2, 0.3]


def test_list_category_embeddings_excludes_self_and_other_category():
    with get_session() as s:
        target = create_problem(s, _problem("타깃", "graph"), status="approved",
                                embedding=[1.0, 0.0])
        sibling = create_problem(s, _problem("형제", "graph"), status="approved",
                                 embedding=[0.0, 1.0])
        # 다른 카테고리 + draft 상태는 모집단에서 빠져야 한다
        create_problem(s, _problem("타카테고리", "dp"), status="approved", embedding=[1.0, 1.0])
        create_problem(s, _problem("미승인", "graph"), status="draft", embedding=[1.0, 1.0])
        no_embed = create_problem(s, _problem("미백필", "graph"), status="approved")

        rows = list_category_embeddings(s, target)
    ids = {rid for rid, _, _, _, _ in rows}
    assert sibling in ids
    assert no_embed in ids  # NULL 임베딩도 포함(호출 측이 건너뜀)
    assert target not in ids  # 자기 자신 제외
    assert len(ids) == 2  # 형제 + 미백필. 타카테고리/미승인 제외
    # 미백필 문제는 embedding None으로 노출
    by_id = {rid: emb for rid, _, emb, _, _ in rows}
    assert by_id[no_embed] is None


def test_list_category_embeddings_carries_level_and_judge_score():
    """RAG exemplar 선정용 level/judge_score를 함께 돌려준다.
    judge_score는 authoring_meta에서 끌어오고, 메타가 없으면 None."""
    with get_session() as s:
        target = create_problem(s, _problem("RAG타깃", "rag"), status="approved",
                                embedding=[1.0, 0.0])
        scored = create_problem(s, _problem("점수있음", "rag"), status="approved",
                                embedding=[0.0, 1.0])
        # judge_score를 authoring_meta에 직접 심는다 (출제 엔진 persist가 하는 것과 동일)
        s.get(ProblemRow, scored).authoring_meta = {"judge_score": 0.82}
        s.add(s.get(ProblemRow, scored))
        s.commit()
        plain = create_problem(s, _problem("메타없음", "rag"), status="approved",
                               embedding=[0.5, 0.5])

        rows = list_category_embeddings(s, target)
    by_id = {rid: (level, score) for rid, _, _, level, score in rows}
    assert by_id[scored] == ("bronze", 0.82)
    assert by_id[plain] == ("bronze", None)  # 메타 없으면 judge_score None


def test_set_problem_embedding_backfills_and_returns_false_for_missing():
    with get_session() as s:
        pid = create_problem(s, _problem("백필대상", "string"), status="approved")
        assert s.get(ProblemRow, pid).embedding is None
        assert set_problem_embedding(s, pid, [0.5, 0.5]) is True
        assert s.get(ProblemRow, pid).embedding == [0.5, 0.5]
        assert set_problem_embedding(s, 999_999, [0.1]) is False


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def test_category_embeddings_requires_auth(client):
    assert client.get("/internal/problems/1/category-embeddings").status_code == 401


def test_category_embeddings_endpoint(client):
    with get_session() as s:
        target = create_problem(s, _problem("E타깃", "geo"), status="approved", embedding=[1.0, 0.0])
        sib = create_problem(s, _problem("E형제", "geo"), status="approved", embedding=[0.0, 1.0])
    r = client.get(f"/internal/problems/{target}/category-embeddings", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert {e["id"] for e in body} == {sib}
    assert body[0]["embedding"] == [0.0, 1.0]


def test_category_embeddings_404(client):
    r = client.get("/internal/problems/999999/category-embeddings", headers=_auth())
    assert r.status_code == 404


def test_patch_embedding_endpoint(client):
    with get_session() as s:
        pid = create_problem(s, _problem("PATCH대상", "tree"), status="approved")
    r = client.patch(
        f"/internal/problems/{pid}/embedding",
        json={"embedding": [0.9, 0.1]},
        headers=_auth(),
    )
    assert r.status_code == 200
    with get_session() as s:
        assert s.get(ProblemRow, pid).embedding == [0.9, 0.1]


def test_patch_embedding_requires_auth(client):
    assert client.patch("/internal/problems/1/embedding", json={"embedding": [0.1]}).status_code == 401


def test_patch_embedding_404(client):
    r = client.patch("/internal/problems/999999/embedding", json={"embedding": [0.1]}, headers=_auth())
    assert r.status_code == 404


def test_create_problem_endpoint_stores_embedding(client):
    payload = {
        "problem": _problem("EP저장", "sort").model_dump(),
        "status": "approved",
        "embedding": [0.3, 0.3, 0.4],
    }
    r = client.post("/internal/problems", json=payload, headers=_auth())
    assert r.status_code == 200
    pid = r.json()["id"]
    with get_session() as s:
        assert s.get(ProblemRow, pid).embedding == [0.3, 0.3, 0.4]
