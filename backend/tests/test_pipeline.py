"""POST /grade → 큐 → 워커 → DB 저장 → GET /grade/{id} 흐름 E2E.
LLM ensemble은 monkeypatch로 mocking하여 Ollama 의존 제거."""
import asyncio
import json

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


def test_happy_path_test_pass_then_llm_ac(
    client: TestClient, seeded_problem_id: int, login_as
):
    login_as(client, "happy@example.com")
    r = client.post("/grade", json={
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
    client: TestClient, seeded_problem_id: int, monkeypatch, login_as
):
    # vote가 호출되면 안 됨을 검증
    called = []

    async def boom_vote(*a, **kw):
        called.append(1)
        raise AssertionError("LLM이 호출되면 안 됨")

    import src.judge.jobs.grading as grading_mod
    monkeypatch.setattr(grading_mod, "vote", boom_vote)

    login_as(client, "test-fail@example.com")
    r = client.post("/grade", json={
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
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n + 99)\n",  # 또 오답
    })
    assert r2.status_code == 202


def test_already_solved_blocks_resubmission(
    client: TestClient, seeded_problem_id: int, login_as
):
    login_as(client, "solver@example.com")
    body = {
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n * 2)\n",
    }
    r = client.post("/grade", json=body)
    assert r.status_code == 202
    _wait_done(client, r.json()["submission_id"])

    # 두 번째 시도는 409 (이미 해결)
    r2 = client.post("/grade", json=body)
    assert r2.status_code == 409


def test_sse_streams_until_done(
    client: TestClient, seeded_problem_id: int, login_as
):
    login_as(client, "sse@example.com")
    r = client.post("/grade", json={
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n * 2)\n",
    })
    assert r.status_code == 202
    sub_id = r.json()["submission_id"]

    events = []
    with client.stream("GET", f"/grade/{sub_id}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: "):])
            events.append(payload)
            if payload["status"] in ("done", "failed"):
                break

    assert events, "SSE stream produced no data events"
    terminal = events[-1]
    assert terminal["status"] == "done"
    assert terminal["final_verdict"] == "AC"
    assert terminal["points_awarded"] is not None
    statuses = [e["status"] for e in events]
    # 큐가 워커 처리보다 빠른 경우 첫 스냅샷이 이미 done일 수 있음 — 그래도 OK.
    assert statuses[-1] == "done"


def test_sse_404_for_unknown_submission(client: TestClient):
    r = client.get("/grade/999999/events")
    assert r.status_code == 404


def test_rejects_oversized_code(client: TestClient, seeded_problem_id: int, login_as):
    """64KB 상한을 초과한 코드는 Pydantic 단계(422)에서 차단 — 큐/DB까지 가지 않음."""
    from src.schemas import MAX_CODE_LENGTH

    login_as(client, "oversize@example.com")
    huge = "x = 1\n" * (MAX_CODE_LENGTH // 6 + 100)  # 약 12K줄, ≈ 70KB
    assert len(huge) > MAX_CODE_LENGTH
    r = client.post("/grade", json={
        "problem_id": seeded_problem_id,
        "code": huge,
    })
    assert r.status_code == 422


def test_rejects_empty_code(client: TestClient, seeded_problem_id: int, login_as):
    login_as(client, "empty@example.com")
    r = client.post("/grade", json={
        "problem_id": seeded_problem_id,
        "code": "",
    })
    assert r.status_code == 422


def test_accepts_code_at_limit(client: TestClient, seeded_problem_id: int, login_as):
    """상한 이하라면 통과해야 함 — boundary 회귀 방지."""
    from src.schemas import MAX_CODE_LENGTH

    login_as(client, "atlimit@example.com")
    # 실제 동작하는 코드 + 의미없는 주석으로 정확히 상한 근처까지 채움
    base = "n = int(input())\nprint(n * 2)\n"
    pad = "# " + "p" * (MAX_CODE_LENGTH - len(base) - 4) + "\n"
    code = base + pad
    assert len(code) <= MAX_CODE_LENGTH
    r = client.post("/grade", json={
        "problem_id": seeded_problem_id,
        "code": code,
    })
    assert r.status_code == 202


def test_grade_requires_auth(client: TestClient, seeded_problem_id: int):
    """쿠키 없으면 401 — body가 valid해도 dep에서 막힘."""
    r = client.post("/grade", json={
        "problem_id": seeded_problem_id,
        "code": "print('x')\n",
    })
    assert r.status_code == 401
