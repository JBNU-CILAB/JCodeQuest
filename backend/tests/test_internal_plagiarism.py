"""표절 검토 internal 엔드포인트 — run 생성/갱신, pair bulk insert/목록/상세/검토 상태.
인증(Bearer JCQ_INTERNAL_SECRET) 가드 포함."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


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


def test_plagiarism_run_and_pairs_lifecycle(client):
    # run 생성 (멱등)
    r = client.post(
        "/internal/plagiarism/runs",
        headers=_auth(),
        json={"id": "plag_1", "problem_id": 3, "problem_title": "사칙연산", "submission_count": 4,
              "config": {"similarity_threshold": 0.7}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "running"
    # 멱등 재호출
    assert client.post("/internal/plagiarism/runs", headers=_auth(),
                       json={"id": "plag_1", "problem_id": 3}).status_code == 200

    # 의심 쌍 bulk insert
    r2 = client.post(
        "/internal/plagiarism/pairs",
        headers=_auth(),
        json={"pairs": [
            {"run_id": "plag_1", "problem_id": 3, "submission_a_id": 10, "submission_b_id": 20,
             "user_a_id": 1, "user_b_id": 2, "similarity": 0.92, "longest_fragment": 40,
             "total_overlap": 88, "fragments": [{"a_lines": [1, 12], "b_lines": [3, 14]}]},
            {"run_id": "plag_1", "problem_id": 3, "submission_a_id": 10, "submission_b_id": 30,
             "user_a_id": 1, "user_b_id": 3, "similarity": 0.55, "longest_fragment": 10,
             "total_overlap": 22, "fragments": []},
        ]},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["inserted"] == 2

    # run 갱신
    r3 = client.patch("/internal/plagiarism/runs/plag_1", headers=_auth(),
                      json={"status": "done", "pair_count": 2, "flagged_count": 2})
    assert r3.status_code == 200 and r3.json()["flagged_count"] == 2

    # 검토 큐 목록 (유사도 내림차순)
    lst = client.get("/internal/plagiarism/pairs", headers=_auth(), params={"problem_id": 3})
    assert lst.status_code == 200
    pairs = lst.json()
    assert len(pairs) == 2
    assert pairs[0]["similarity"] >= pairs[1]["similarity"]  # 0.92 먼저
    pid = pairs[0]["id"]

    # 검토 상태 갱신
    up = client.patch(f"/internal/plagiarism/pairs/{pid}", headers=_auth(),
                      json={"status": "confirmed", "admin_notes": "동일 구조 + 동일 주석 오타"})
    assert up.status_code == 200 and up.json()["status"] == "confirmed"

    # status 필터
    conf = client.get("/internal/plagiarism/pairs", headers=_auth(), params={"status": "confirmed"})
    assert {p["id"] for p in conf.json()} == {pid}


def test_plagiarism_auth_and_404(client):
    assert client.get("/internal/plagiarism/pairs").status_code == 401
    assert client.post("/internal/plagiarism/pairs", json={"pairs": []}).status_code == 401
    assert client.patch("/internal/plagiarism/runs/nope", headers=_auth(),
                        json={"status": "done"}).status_code == 404
    assert client.patch("/internal/plagiarism/pairs/999999", headers=_auth(),
                        json={"status": "confirmed"}).status_code == 404
