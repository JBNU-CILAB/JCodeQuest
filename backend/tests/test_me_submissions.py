"""GET /problems/{id}/attempt-status, GET /me/submissions, GET /problems/{id}/my-submissions.

- 인증 게이트 (401)
- 미존재 문제 (404)
- 시도/쿨다운/AC 여부 계산이 attempt_status와 일치
- /me/submissions 페이지네이션, problem_id / verdict 필터
- /my-submissions 가 problem_id 스코프로 동일하게 동작
- 응답에 code 가 노출되지 않음
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import src.storage.submissions as subs
from src.schemas import EnsembleResult, JudgeVote, TestResult
from src.storage import get_session
from src.storage.models import SubmissionRow
from src.storage.submissions import (
    MAX_ATTEMPTS,
    create_submission,
    save_grading,
)


@pytest.fixture
def client():
    from src.main import app
    with TestClient(app) as c:
        yield c


def _ac() -> EnsembleResult:
    return EnsembleResult(
        final_verdict="AC", mode="unanimous",
        votes=[
            JudgeVote(judge_id=jid, verdict="AC", intent_match=True,
                      rationale="ok", confidence=1.0)
            for jid in ("Melchior", "Balthasar", "Casper")
        ],
    )


def _sus() -> EnsembleResult:
    return EnsembleResult(
        final_verdict="SUS", mode="unanimous",
        votes=[
            JudgeVote(judge_id=jid, verdict="SUS", intent_match=False,
                      rationale="bad", confidence=0.9)
            for jid in ("Melchior", "Balthasar", "Casper")
        ],
    )


def _ok_results() -> list[TestResult]:
    return [TestResult(ordinal=1, passed=True, status="OK")]


# ───────────────────── attempt-status ─────────────────────


def test_attempt_status_requires_auth(client: TestClient, seeded_problem_id: int):
    r = client.get(f"/problems/{seeded_problem_id}/attempt-status")
    assert r.status_code == 401


def test_attempt_status_404_for_unknown_problem(client: TestClient, login_as):
    login_as(client, "as-404@example.com")
    r = client.get("/problems/999999/attempt-status")
    assert r.status_code == 404


def test_attempt_status_fresh_user(
    client: TestClient, seeded_problem_id: int, login_as
):
    login_as(client, "as-fresh@example.com")
    r = client.get(f"/problems/{seeded_problem_id}/attempt-status")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "problem_id": seeded_problem_id,
        "attempts": 0,
        "remaining": MAX_ATTEMPTS,
        "max_attempts": MAX_ATTEMPTS,
        "solved": False,
        "cooldown_remaining_s": 0.0,
        "can_submit": True,
    }


def test_attempt_status_reflects_sus_attempt(
    client: TestClient, seeded_problem_id: int, login_as
):
    user_id = login_as(client, "as-sus@example.com")
    with get_session() as s:
        sid = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="x"
        )
        save_grading(
            s, sid,
            final_verdict="SUS",
            test_results=_ok_results(),
            ensemble=_sus(),
            points_awarded=0,
        )

    r = client.get(f"/problems/{seeded_problem_id}/attempt-status")
    assert r.status_code == 200
    body = r.json()
    assert body["attempts"] == 1
    assert body["remaining"] == MAX_ATTEMPTS - 1
    assert body["solved"] is False
    assert body["can_submit"] is True  # 쿨다운 0


def test_attempt_status_after_ac_locks_out(
    client: TestClient, seeded_problem_id: int, login_as
):
    user_id = login_as(client, "as-ac@example.com")
    with get_session() as s:
        sid = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="good"
        )
        save_grading(
            s, sid,
            final_verdict="AC",
            test_results=_ok_results(),
            ensemble=_ac(),
            points_awarded=100,
        )

    r = client.get(f"/problems/{seeded_problem_id}/attempt-status")
    body = r.json()
    assert body["solved"] is True
    assert body["can_submit"] is False
    assert body["attempts"] == 1


def test_attempt_status_cooldown_blocks_submit(
    client: TestClient, seeded_problem_id: int, login_as, monkeypatch
):
    """sandbox-fail(=mode None)로도 cooldown 트리거되는지 — attempts는 0이어도 can_submit False."""
    monkeypatch.setattr(subs, "SUBMISSION_COOLDOWN_S", 30.0)
    user_id = login_as(client, "as-cool@example.com")

    with get_session() as s:
        # mode=None인 submission row를 직접 만들어 sandbox-fail 모사
        row = SubmissionRow(
            user_id=user_id,
            problem_id=seeded_problem_id,
            code="boom",
            status="done",
            final_verdict="SUS",
            mode=None,
            test_results=[{"ordinal": 1, "passed": False, "status": "RE"}],
        )
        s.add(row)
        s.commit()

    r = client.get(f"/problems/{seeded_problem_id}/attempt-status")
    body = r.json()
    assert body["attempts"] == 0  # LLM-judged 아님
    assert body["solved"] is False
    assert body["cooldown_remaining_s"] > 0
    assert body["can_submit"] is False


# ───────────────────── /me/submissions ─────────────────────


def test_me_submissions_requires_auth(client: TestClient):
    r = client.get("/me/submissions")
    assert r.status_code == 401


def _seed_submission(
    user_id: int,
    problem_id: int,
    *,
    verdict: str | None,
    mode: str | None = "unanimous",
    points: int | None = None,
    created_at: datetime | None = None,
) -> int:
    """save_grading 우회 — exp 부수효과 없이 정확히 원하는 verdict/시각을 넣는다."""
    with get_session() as s:
        row = SubmissionRow(
            user_id=user_id,
            problem_id=problem_id,
            code="seed",
            status="done",
            final_verdict=verdict,
            mode=mode,
            test_results=[{"ordinal": 1, "passed": verdict == "AC", "status": "OK"}],
            points_awarded=points,
        )
        if created_at is not None:
            row.created_at = created_at
        s.add(row)
        s.commit()
        s.refresh(row)
        assert row.id is not None
        return row.id


def test_me_submissions_newest_first_and_pagination(
    client: TestClient, seeded_problem_id: int, login_as
):
    user_id = login_as(client, "ms-list@example.com")
    base = datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc)
    sids = [
        _seed_submission(
            user_id, seeded_problem_id, verdict="SUS",
            created_at=base + timedelta(seconds=i),
        )
        for i in range(5)
    ]

    r = client.get("/me/submissions")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["limit"] == 20
    assert body["offset"] == 0
    # 최신순 (created_at desc) → 마지막에 넣은 게 먼저
    assert [it["id"] for it in body["items"]] == list(reversed(sids))
    # code 노출 금지
    assert "code" not in body["items"][0]
    assert "seed" not in r.text

    # 페이지네이션
    r = client.get("/me/submissions", params={"limit": 2, "offset": 2})
    body = r.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert [it["id"] for it in body["items"]] == list(reversed(sids))[2:4]


def test_me_submissions_filters_by_problem_and_verdict(
    client: TestClient, sample_problem, login_as
):
    from src.storage.problems import create_problem

    with get_session() as s:
        p1 = create_problem(s, sample_problem, status="approved")
        p2 = create_problem(s, sample_problem, status="approved")

    user_id = login_as(client, "ms-filter@example.com")
    _seed_submission(user_id, p1, verdict="AC", points=100)
    _seed_submission(user_id, p1, verdict="SUS")
    _seed_submission(user_id, p2, verdict="SUS")
    _seed_submission(user_id, p2, verdict="AC", points=100)

    # problem 필터
    r = client.get("/me/submissions", params={"problem_id": p1})
    body = r.json()
    assert body["total"] == 2
    assert {it["problem_id"] for it in body["items"]} == {p1}

    # verdict 필터
    r = client.get("/me/submissions", params={"verdict": "AC"})
    body = r.json()
    assert body["total"] == 2
    assert all(it["final_verdict"] == "AC" for it in body["items"])

    # 조합
    r = client.get(
        "/me/submissions", params={"problem_id": p2, "verdict": "AC"}
    )
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["problem_id"] == p2
    assert body["items"][0]["final_verdict"] == "AC"
    assert body["items"][0]["points_awarded"] == 100


def test_me_submissions_scoped_to_caller_only(
    client: TestClient, seeded_problem_id: int, login_as
):
    """다른 user의 제출이 섞여 나오지 않는다."""
    other_id = login_as(client, "ms-other@example.com")
    _seed_submission(other_id, seeded_problem_id, verdict="AC", points=100)

    client.cookies.clear()
    login_as(client, "ms-mine@example.com")
    r = client.get("/me/submissions")
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_me_submissions_rejects_invalid_pagination(
    client: TestClient, login_as
):
    login_as(client, "ms-bad@example.com")
    assert client.get("/me/submissions", params={"limit": 0}).status_code == 422
    assert client.get("/me/submissions", params={"limit": 1000}).status_code == 422
    assert client.get("/me/submissions", params={"offset": -1}).status_code == 422


# ───────────────────── /problems/{id}/my-submissions ─────────────────────


def test_my_submissions_per_problem_404_unknown(
    client: TestClient, login_as
):
    login_as(client, "myp-404@example.com")
    r = client.get("/problems/999999/my-submissions")
    assert r.status_code == 404


def test_my_submissions_per_problem_requires_auth(
    client: TestClient, seeded_problem_id: int
):
    r = client.get(f"/problems/{seeded_problem_id}/my-submissions")
    assert r.status_code == 401


def test_my_submissions_per_problem_scopes_correctly(
    client: TestClient, sample_problem, login_as
):
    from src.storage.problems import create_problem

    with get_session() as s:
        p1 = create_problem(s, sample_problem, status="approved")
        p2 = create_problem(s, sample_problem, status="approved")

    user_id = login_as(client, "myp-scope@example.com")
    sid_p1_sus = _seed_submission(user_id, p1, verdict="SUS")
    _seed_submission(user_id, p2, verdict="AC", points=100)

    r = client.get(f"/problems/{p1}/my-submissions")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == sid_p1_sus
    assert body["items"][0]["problem_id"] == p1
    # 다른 문제(p2)의 AC 제출이 새지 않음
    assert all(it["problem_id"] == p1 for it in body["items"])
