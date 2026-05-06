"""POST /grade → 큐 → 워커 → DB 저장 → GET /grade/{id} 흐름 E2E.
LLM ensemble은 monkeypatch로 mocking하여 Ollama 의존 제거."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from src.schemas import EnsembleResult, JudgeVote, Problem, TestResult


def _fake_ac():
    return EnsembleResult(
        final_verdict="AC",
        mode="unanimous",
        votes=[
            JudgeVote(
                judge_id=jid,
                verdict="AC",
                intent_match=True,
                rationale="looks correct",
                confidence=1.0,
            )
            for jid in ("Melchior", "Balthasar", "Casper")
        ],
    )


@pytest.fixture
def client(monkeypatch):
    # judge.jobs.grading 안에서 import해서 쓰는 vote 심볼을 갈아끼움
    async def fake_vote(problem, code, test_results, base_url=None):
        return _fake_ac()

    import src.judge.jobs.grading as grading_mod
    monkeypatch.setattr(grading_mod, "vote", fake_vote)

    from src.main import app
    with TestClient(app) as c:
        yield c


def _wait_done(client: TestClient, sub_id: int, timeout_s: float = 10.0) -> dict:
    import time
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        r = client.get(f"/grade/{sub_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for submission {sub_id}")


def test_happy_path_test_pass_then_llm_ac(client: TestClient, seeded_problem_id: int):
    r = client.post("/grade", json={
        "user_id": 1,
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n * 2)\n",
    })
    assert r.status_code == 202, r.text
    sub_id = r.json()["submission_id"]

    body = _wait_done(client, sub_id)
    assert body["status"] == "done"
    assert body["final_verdict"] == "AC"
    assert body["points_awarded"] is not None and body["points_awarded"] > 0
    assert body["ensemble"] is not None
    assert body["ensemble"]["mode"] == "unanimous"
    # 모든 테스트 통과 확인
    trs = body["test_results"]
    assert len(trs) == 3
    assert all(t["passed"] for t in trs)


def test_test_fail_skips_llm_and_doesnt_count_attempt(
    client: TestClient, seeded_problem_id: int, monkeypatch
):
    # vote가 호출되면 안 됨을 검증
    called = []

    async def boom_vote(*a, **kw):
        called.append(1)
        raise AssertionError("LLM이 호출되면 안 됨")

    import src.judge.jobs.grading as grading_mod
    monkeypatch.setattr(grading_mod, "vote", boom_vote)

    r = client.post("/grade", json={
        "user_id": 2,
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n + 1)\n",  # 오답
    })
    assert r.status_code == 202
    sub_id = r.json()["submission_id"]

    body = _wait_done(client, sub_id)
    assert body["status"] == "done"
    assert body["final_verdict"] == "SUS"
    assert body["ensemble"] is None
    assert body["points_awarded"] is None
    assert called == []  # vote가 안 불렸어야

    # 시도 카운트는 차감되지 않아야 — 다시 똑같이 또 보내도 통과해야 함
    r2 = client.post("/grade", json={
        "user_id": 2,
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n + 99)\n",  # 또 오답
    })
    assert r2.status_code == 202


def test_already_solved_blocks_resubmission(
    client: TestClient, seeded_problem_id: int
):
    body = {
        "user_id": 7,
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n * 2)\n",
    }
    r = client.post("/grade", json=body)
    assert r.status_code == 202
    _wait_done(client, r.json()["submission_id"])

    # 두 번째 시도는 409 (이미 해결)
    r2 = client.post("/grade", json=body)
    assert r2.status_code == 409
