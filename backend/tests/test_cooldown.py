"""제출 쿨다운(=같은 user/problem 사이 최소 간격) 동작 검증.

단위 테스트는 `cooldown_remaining_s()` 계산 자체를 보고,
API 테스트는 두 번째 제출이 429 + Retry-After 로 막히는지 확인한다."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import src.storage.submissions as subs
from src.schemas import EnsembleResult, JudgeVote
from src.storage.submissions import AttemptStatus


# ───────────────────── 단위: cooldown_remaining_s ─────────────────────


def test_cooldown_zero_when_never_submitted():
    a = AttemptStatus(attempts=0, solved=False, last_submitted_at=None)
    assert a.cooldown_remaining_s() == 0.0


def test_cooldown_full_just_after_submit(monkeypatch):
    monkeypatch.setattr(subs, "SUBMISSION_COOLDOWN_S", 10.0)
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    a = AttemptStatus(
        attempts=0, solved=False,
        last_submitted_at=now - timedelta(seconds=0.1),
    )
    remaining = a.cooldown_remaining_s(now=now)
    # 거의 풀 쿨다운 — 9.8 ~ 10.0 사이
    assert 9.5 <= remaining <= 10.0


def test_cooldown_expired_after_full_interval(monkeypatch):
    monkeypatch.setattr(subs, "SUBMISSION_COOLDOWN_S", 10.0)
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    a = AttemptStatus(
        attempts=0, solved=False,
        last_submitted_at=now - timedelta(seconds=15),
    )
    assert a.cooldown_remaining_s(now=now) == 0.0


def test_cooldown_handles_naive_last_submitted_at(monkeypatch):
    """SQLite에서 retrieve된 created_at은 timezone naive일 수 있음 — UTC로 가정해야 함."""
    monkeypatch.setattr(subs, "SUBMISSION_COOLDOWN_S", 10.0)
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    naive_last = (now - timedelta(seconds=3)).replace(tzinfo=None)
    a = AttemptStatus(attempts=0, solved=False, last_submitted_at=naive_last)
    remaining = a.cooldown_remaining_s(now=now)
    assert 6.5 <= remaining <= 7.5


def test_cooldown_disabled_when_constant_zero(monkeypatch):
    monkeypatch.setattr(subs, "SUBMISSION_COOLDOWN_S", 0.0)
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    a = AttemptStatus(
        attempts=0, solved=False,
        last_submitted_at=now - timedelta(seconds=0.001),
    )
    assert a.cooldown_remaining_s(now=now) == 0.0


# ───────────────────── 통합: POST /grade 두 번 연속 ─────────────────────


def _fake_ac() -> EnsembleResult:
    return EnsembleResult(
        final_verdict="AC", mode="unanimous",
        votes=[
            JudgeVote(
                judge_id=jid, verdict="AC", intent_match=True,
                rationale="ok", confidence=1.0,
            )
            for jid in ("Melchior", "Balthasar", "Casper")
        ],
    )


@pytest.fixture
def client_with_cooldown(monkeypatch):
    """기본 autouse 쿨다운=0을 다시 켜고, LLM도 mock."""
    # 기본 쿨다운 0 fixture 위에 덮어쓰기 — autouse가 먼저 돌고 이게 나중에 덮음
    monkeypatch.setattr(subs, "SUBMISSION_COOLDOWN_S", 30.0)

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


def test_second_submit_blocked_by_cooldown(
    client_with_cooldown: TestClient, seeded_problem_id: int, login_as
):
    # 첫 user의 AC 한 번
    login_as(client_with_cooldown, "cooldown-1@example.com")
    body = {
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n * 2)\n",
    }
    r1 = client_with_cooldown.post("/grade", json=body)
    assert r1.status_code == 202
    _wait_done(client_with_cooldown, r1.json()["submission_id"])

    # 다른 user로 전환 후 한 번 제출 → 즉시 재제출이 쿨다운으로 막히는지
    client_with_cooldown.cookies.clear()
    login_as(client_with_cooldown, "cooldown-2@example.com")
    body2 = {
        "problem_id": seeded_problem_id,
        "code": "n = int(input())\nprint(n + 1)\n",  # WA — sandbox-fail 경로
    }
    r2 = client_with_cooldown.post("/grade", json=body2)
    assert r2.status_code == 202
    _wait_done(client_with_cooldown, r2.json()["submission_id"])

    # 같은 user/problem 즉시 재제출 → 쿨다운 429
    r3 = client_with_cooldown.post("/grade", json={**body2, "code": "x"})
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers
    assert int(r3.headers["Retry-After"]) >= 1
    assert "초 후" in r3.json()["detail"]


def test_cooldown_blocks_even_after_sandbox_fail(
    client_with_cooldown: TestClient, seeded_problem_id: int, login_as
):
    """sandbox-fail 제출도 쿨다운 트리거 — 정찰 차단의 핵심 시나리오."""
    login_as(client_with_cooldown, "cooldown-sf@example.com")
    body = {
        "problem_id": seeded_problem_id,
        "code": "1/0\n",  # RE
    }
    r1 = client_with_cooldown.post("/grade", json=body)
    assert r1.status_code == 202
    _wait_done(client_with_cooldown, r1.json()["submission_id"])

    # 즉시 재제출 → sandbox-fail 이후에도 쿨다운 작동해야 함
    r2 = client_with_cooldown.post(
        "/grade", json={**body, "code": "print('x')\n"}
    )
    assert r2.status_code == 429
