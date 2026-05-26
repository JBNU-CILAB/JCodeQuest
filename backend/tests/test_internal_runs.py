"""출제 파이프라인 run 영속화 엔드포인트 (admin RunsView · forensics).

- POST   /internal/runs            run 기록 생성 (멱등)
- PATCH  /internal/runs/{id}        부분 갱신 (node_states 전체 교체)
- GET    /internal/runs             목록 (status/problem_id 필터)
- GET    /internal/runs/{id}        상세 (node_states 포함)
- 인증(Bearer JCQ_INTERNAL_SECRET) 가드 / 404
"""
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


def test_run_lifecycle_create_update_get(client):
    rid = "run_abc123"
    # create
    r = client.post(
        "/internal/runs",
        headers=_auth(),
        json={
            "id": rid,
            "trace_id": "trace-1",
            "problem_id": 12,
            "problem_title": "떡볶이 떡 자르기",
            "target_count": 5,
            "by_user": "kim_jh",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "running"
    assert r.json()["saved_count"] == 0

    # create 멱등 — 같은 id 재호출은 기존 row
    r2 = client.post("/internal/runs", headers=_auth(), json={"id": rid, "target_count": 99})
    assert r2.status_code == 200
    assert r2.json()["target_count"] == 5  # 덮어쓰지 않음

    # update: 실패로 종료 + node_states
    node_states = {
        "fetch_problem": {"status": "done", "duration_ms": 80, "retries": 0},
        "judge_candidates": {
            "status": "failed",
            "duration_ms": 13200,
            "retries": 2,
            "error": "OllamaError: connection refused",
            "candidate_results": [{"idx": 1, "status": "fail", "note": "2/3"}],
        },
    }
    r3 = client.patch(
        f"/internal/runs/{rid}",
        headers=_auth(),
        json={
            "status": "failed",
            "failed_at_node": "judge_candidates",
            "total_duration_ms": 27410,
            "ended_at": "2026-05-26T10:00:00Z",
            "errors": ["OllamaError: connection refused"],
            "node_states": node_states,
        },
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "failed"
    assert r3.json()["failed_at_node"] == "judge_candidates"

    # get detail — node_states 보존
    r4 = client.get(f"/internal/runs/{rid}", headers=_auth())
    assert r4.status_code == 200
    body = r4.json()
    assert body["node_states"]["judge_candidates"]["error"].startswith("OllamaError")
    assert body["errors"] == ["OllamaError: connection refused"]
    assert body["total_duration_ms"] == 27410


def test_run_list_filters_by_status(client):
    client.post("/internal/runs", headers=_auth(), json={"id": "r_done", "problem_id": 1})
    client.patch("/internal/runs/r_done", headers=_auth(), json={"status": "done"})
    client.post("/internal/runs", headers=_auth(), json={"id": "r_run", "problem_id": 1})

    done = client.get("/internal/runs", headers=_auth(), params={"status": "done"})
    assert done.status_code == 200
    ids = {x["id"] for x in done.json()}
    assert "r_done" in ids and "r_run" not in ids

    by_problem = client.get("/internal/runs", headers=_auth(), params={"problem_id": 1})
    assert {x["id"] for x in by_problem.json()} >= {"r_done", "r_run"}


def test_run_auth_and_404(client):
    # 인증 누락
    assert client.get("/internal/runs").status_code == 401
    assert client.post("/internal/runs", json={"id": "x"}).status_code == 401
    # 없는 run
    assert client.get("/internal/runs/nope", headers=_auth()).status_code == 404
    assert (
        client.patch("/internal/runs/nope", headers=_auth(), json={"status": "done"}).status_code
        == 404
    )


def test_delete_run_single(client):
    client.post("/internal/runs", headers=_auth(), json={"id": "r_del", "problem_id": 7})
    # 삭제
    r = client.delete("/internal/runs/r_del", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    # 삭제 후 조회 404
    assert client.get("/internal/runs/r_del", headers=_auth()).status_code == 404
    # 없는 run 삭제 → 404
    assert client.delete("/internal/runs/nope", headers=_auth()).status_code == 404
    # 인증 누락
    assert client.delete("/internal/runs/r_del").status_code == 401


def test_bulk_delete_by_ids(client):
    for rid in ("b1", "b2", "b3"):
        client.post("/internal/runs", headers=_auth(), json={"id": rid})

    # 선택한 2건 + 없는 id 1건 → 존재하는 것만 삭제(2건)
    r = client.post(
        "/internal/runs/delete", headers=_auth(), json={"ids": ["b1", "b3", "nope"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["deleted_count"] == 2
    remaining = {x["id"] for x in client.get("/internal/runs", headers=_auth()).json()}
    assert "b1" not in remaining and "b3" not in remaining
    assert "b2" in remaining  # 선택 안 한 건 남음

    # 빈 목록은 0건 — no-op
    r2 = client.post("/internal/runs/delete", headers=_auth(), json={"ids": []})
    assert r2.status_code == 200 and r2.json()["deleted_count"] == 0

    # 인증 누락
    assert client.post("/internal/runs/delete", json={"ids": ["b2"]}).status_code == 401
