"""GET /internal/stats/verdicts, /internal/stats/judges 라우터 검사.

- 인증 (Bearer JCQ_INTERNAL_SECRET) 가드
- 버킷별 zero-fill + AC/SUS/failed/pending 카운트
- judge_id별 동의율 + unanimous/split 카운트
- 잘못된 bucket / 범위 over-cap → 400/422
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.schemas import EnsembleResult, JudgeVote, TestResult
from src.storage import get_session
from src.storage.models import SubmissionRow
from src.storage.problems import create_problem
from src.storage.submissions import create_submission, save_grading


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


def _vote(jid: str, verdict: str) -> JudgeVote:
    return JudgeVote(
        judge_id=jid, verdict=verdict, intent_match=verdict == "AC",
        rationale="t", confidence=0.9,
    )


def _ensemble(verdicts: dict[str, str], final: str) -> EnsembleResult:
    return EnsembleResult(
        final_verdict=final,  # type: ignore[arg-type]
        mode="unanimous" if len(set(verdicts.values())) == 1 else "majority",
        votes=[_vote(jid, v) for jid, v in verdicts.items()],
    )


def _seed_problem_user(sample_problem, make_user) -> tuple[int, int]:
    with get_session() as s:
        pid = create_problem(s, sample_problem, status="approved")
    uid = make_user()
    return pid, uid


def _mk_submission(uid: int, pid: int, *, ensemble: EnsembleResult | None,
                   final: str, status_override: str | None = None,
                   created_at: datetime | None = None) -> int:
    with get_session() as s:
        sid = create_submission(s, user_id=uid, problem_id=pid, code="x = 1\n")
        # 시각을 직접 조작 — created_at은 default_factory라 model에 박혀버렸으니 update.
        if created_at is not None:
            row = s.get(SubmissionRow, sid)
            assert row is not None
            row.created_at = created_at
            s.add(row)
            s.commit()
        results = [TestResult(ordinal=1, passed=True, status="OK", elapsed_ms=1, peak_memory_kb=1000)]
        save_grading(s, sid, final_verdict=final, test_results=results, ensemble=ensemble)
        if status_override is not None:
            row = s.get(SubmissionRow, sid)
            assert row is not None
            row.status = status_override
            s.add(row)
            s.commit()
    return sid


def test_stats_requires_auth(client):
    r = client.get("/internal/stats/verdicts")
    assert r.status_code == 401


def test_stats_verdicts_buckets_and_counts(client, sample_problem, make_user):
    pid, uid = _seed_problem_user(sample_problem, make_user)
    now = datetime.now(timezone.utc)
    # 같은 날 AC 2, SUS 1, failed 1
    for _ in range(2):
        _mk_submission(uid, pid, ensemble=_ensemble(
            {"Melchior": "AC", "Balthasar": "AC", "Casper": "AC"}, "AC"), final="AC",
            created_at=now - timedelta(hours=1))
    _mk_submission(uid, pid, ensemble=_ensemble(
        {"Melchior": "SUS", "Balthasar": "SUS", "Casper": "SUS"}, "SUS"), final="SUS",
        created_at=now - timedelta(hours=2))
    _mk_submission(uid, pid, ensemble=None, final="SUS",
                   status_override="failed", created_at=now - timedelta(hours=3))

    r = client.get(
        "/internal/stats/verdicts",
        params={"bucket": "day", "problem_id": pid},
        headers=_auth(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bucket"] == "day"
    # 오늘 버킷 한 칸이 들어 있어야 한다.
    today_key = now.strftime("%Y-%m-%d")
    today = next((b for b in body["series"] if b["bucket"] == today_key), None)
    assert today is not None
    assert today["ac"] == 2
    assert today["sus"] == 1
    assert today["failed"] == 1
    assert today["total"] == 4

    # zero-fill: 14일치 day 버킷이 채워져야 함 (최소 14, ±1 허용)
    assert len(body["series"]) >= 14


def test_stats_judges_agreement_and_split(client, sample_problem, make_user):
    pid, uid = _seed_problem_user(sample_problem, make_user)
    now = datetime.now(timezone.utc)

    # 1) 3:0 합의 AC
    _mk_submission(uid, pid, ensemble=_ensemble(
        {"Melchior": "AC", "Balthasar": "AC", "Casper": "AC"}, "AC"), final="AC",
        created_at=now - timedelta(hours=1))
    # 2) 2:1 majority — Casper만 다름. final=AC. Casper의 agree=0.
    _mk_submission(uid, pid, ensemble=_ensemble(
        {"Melchior": "AC", "Balthasar": "AC", "Casper": "SUS"}, "AC"), final="AC",
        created_at=now - timedelta(hours=2))
    # 3) 3:0 SUS
    _mk_submission(uid, pid, ensemble=_ensemble(
        {"Melchior": "SUS", "Balthasar": "SUS", "Casper": "SUS"}, "SUS"), final="SUS",
        created_at=now - timedelta(hours=3))

    r = client.get(
        "/internal/stats/judges",
        params={"bucket": "day", "problem_id": pid},
        headers=_auth(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["judge_ids"] == ["Balthasar", "Casper", "Melchior"]
    today_key = now.strftime("%Y-%m-%d")
    today = next((b for b in body["series"] if b["bucket"] == today_key), None)
    assert today is not None
    assert today["total_with_votes"] == 3
    assert today["unanimous"] == 2
    assert today["split"] == 1
    # Melchior: 2 AC + 1 SUS, 모두 final과 일치 → agree=3
    assert today["judges"]["Melchior"] == {"ac": 2, "sus": 1, "agree_with_final": 3}
    # Casper: 1 AC + 2 SUS, 2번 케이스에서 final=AC인데 SUS 투표 → agree=2
    assert today["judges"]["Casper"] == {"ac": 1, "sus": 2, "agree_with_final": 2}


def test_stats_verdicts_excludes_other_problem(client, sample_problem, make_user):
    pid, uid = _seed_problem_user(sample_problem, make_user)
    # 다른 문제 행은 problem_id 필터로 제외돼야 한다.
    other_problem = sample_problem.model_copy(update={"title": "다른 문제"})
    with get_session() as s:
        other_pid = create_problem(s, other_problem, status="approved")
    now = datetime.now(timezone.utc)
    _mk_submission(uid, pid, ensemble=_ensemble(
        {"Melchior": "AC", "Balthasar": "AC", "Casper": "AC"}, "AC"), final="AC",
        created_at=now - timedelta(hours=1))
    _mk_submission(uid, other_pid, ensemble=_ensemble(
        {"Melchior": "AC", "Balthasar": "AC", "Casper": "AC"}, "AC"), final="AC",
        created_at=now - timedelta(hours=1))

    r = client.get(
        "/internal/stats/verdicts",
        params={"bucket": "day", "problem_id": pid},
        headers=_auth(),
    )
    assert r.status_code == 200
    total = sum(b["total"] for b in r.json()["series"])
    assert total == 1


def test_stats_invalid_bucket(client):
    r = client.get(
        "/internal/stats/verdicts",
        params={"bucket": "minute"},
        headers=_auth(),
    )
    assert r.status_code == 422


def test_stats_range_cap_exceeded(client):
    # hour bucket의 cap은 14일. 30일은 거부돼야 한다.
    now = datetime.now(timezone.utc)
    r = client.get(
        "/internal/stats/verdicts",
        params={
            "bucket": "hour",
            "since": (now - timedelta(days=30)).isoformat(),
            "until": now.isoformat(),
        },
        headers=_auth(),
    )
    assert r.status_code == 400
    assert "cap" in r.text


def test_stats_judges_ignores_votes_null(client, sample_problem, make_user):
    pid, uid = _seed_problem_user(sample_problem, make_user)
    now = datetime.now(timezone.utc)
    # ensemble=None 인 제출은 judges 통계에서 제외돼야 한다.
    _mk_submission(uid, pid, ensemble=None, final="SUS",
                   created_at=now - timedelta(hours=1))
    r = client.get(
        "/internal/stats/judges",
        params={"bucket": "day", "problem_id": pid},
        headers=_auth(),
    )
    assert r.status_code == 200
    total = sum(b["total_with_votes"] for b in r.json()["series"])
    assert total == 0
