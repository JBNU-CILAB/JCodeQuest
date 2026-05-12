"""GET /leaderboard 누적/주간 집계 검사.

- period=all: UserRow.exp 내림차순. exp==0인 유저는 제외.
- period=week: 이번 ISO 주차에 기록된 points_awarded 합. 지난 주에 얻은 EXP는 빠져야 함.
- 동점은 user_id 오름차순.
- limit 적용.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.schemas import EnsembleResult, JudgeVote, TestResult
from src.storage import get_session
from src.storage.models import SubmissionRow, iso_week_of
from src.storage.submissions import create_submission, save_grading
from src.storage.users import bump_user_exp


@pytest.fixture
def client():
    from src.main import app
    with TestClient(app) as c:
        yield c


def _ac_ensemble() -> EnsembleResult:
    return EnsembleResult(
        final_verdict="AC",
        mode="unanimous",
        votes=[
            JudgeVote(
                judge_id=jid, verdict="AC", intent_match=True,
                rationale="ok", confidence=1.0,
            )
            for jid in ("Melchior", "Balthasar", "Casper")
        ],
    )


def _ok_results() -> list[TestResult]:
    return [
        TestResult(ordinal=1, passed=True, status="OK", elapsed_ms=10, peak_memory_kb=8000),
    ]


# ───────────────────────── period=all ─────────────────────────


def test_leaderboard_all_orders_by_exp_desc(client: TestClient, make_user):
    a = make_user("alice")
    b = make_user("bob")
    c = make_user("carol")
    with get_session() as s:
        bump_user_exp(s, a, delta=50)
        bump_user_exp(s, b, delta=200)
        bump_user_exp(s, c, delta=120)
        s.commit()

    r = client.get("/leaderboard", params={"period": "all"})
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "all"
    assert body["week"] is None
    # bob > carol > alice
    ordered_ids = [e["user_id"] for e in body["entries"]]
    # 다른 테스트에서 만들어 둔 유저가 섞일 수 있으니 a/b/c의 상대 순서만 확인
    pos = {uid: i for i, uid in enumerate(ordered_ids)}
    assert pos[b] < pos[c] < pos[a]
    # rank는 1-based 연속
    ranks = [e["rank"] for e in body["entries"]]
    assert ranks == list(range(1, len(ranks) + 1))


def test_leaderboard_all_excludes_zero_exp(client: TestClient, make_user):
    zero = make_user("noobie")  # exp=0
    scorer = make_user("scorer")
    with get_session() as s:
        bump_user_exp(s, scorer, delta=10)
        s.commit()

    r = client.get("/leaderboard", params={"period": "all"})
    ids = {e["user_id"] for e in r.json()["entries"]}
    assert scorer in ids
    assert zero not in ids


def test_leaderboard_all_tie_breaks_by_user_id_asc(client: TestClient, make_user):
    first = make_user("first")
    second = make_user("second")
    with get_session() as s:
        bump_user_exp(s, first, delta=77)
        bump_user_exp(s, second, delta=77)
        s.commit()

    body = client.get("/leaderboard", params={"period": "all"}).json()
    ids = [e["user_id"] for e in body["entries"]]
    pos = {uid: i for i, uid in enumerate(ids)}
    assert pos[first] < pos[second]


def test_leaderboard_all_respects_limit(client: TestClient, make_user):
    users = [make_user(f"u{i}") for i in range(5)]
    with get_session() as s:
        for i, uid in enumerate(users):
            bump_user_exp(s, uid, delta=10 + i)
        s.commit()

    body = client.get("/leaderboard", params={"period": "all", "limit": 2}).json()
    assert len(body["entries"]) == 2


# ───────────────────────── period=week ─────────────────────────


def _ac_submission(user_id: int, problem_id: int, *, points: int) -> int:
    with get_session() as s:
        sid = create_submission(s, user_id=user_id, problem_id=problem_id, code="ok")
        save_grading(
            s, sid,
            final_verdict="AC",
            test_results=_ok_results(),
            ensemble=_ac_ensemble(),
            points_awarded=points,
        )
    return sid


def _backdate_submission(submission_id: int, when: datetime) -> None:
    """SubmissionRow.created_at은 default_factory가 박으므로 테스트는 직접 갈아끼움."""
    with get_session() as s:
        row = s.get(SubmissionRow, submission_id)
        assert row is not None
        row.created_at = when
        s.add(row)
        s.commit()


def test_leaderboard_week_sums_points_in_current_iso_week(
    client: TestClient, make_user, seeded_problem_id
):
    user = make_user("weekly")
    sid = _ac_submission(user, seeded_problem_id, points=150)
    # created_at은 default로 '지금' — 이번 주에 들어옴
    body = client.get("/leaderboard", params={"period": "week"}).json()
    assert body["period"] == "week"
    assert body["week"] == iso_week_of(datetime.now(timezone.utc))

    entry = next(e for e in body["entries"] if e["user_id"] == user)
    assert entry["points"] == 150
    assert entry["rank"] >= 1

    # 응답 형태
    assert set(entry.keys()) == {"rank", "user_id", "display_name", "tier", "points"}


def test_leaderboard_week_excludes_prior_week_submissions(
    client: TestClient, make_user, sample_problem
):
    """지난 주에 첫 AC를 받은 유저는 이번 주 리더보드에 나타나지 않아야 한다."""
    from src.storage.problems import create_problem

    # 별도 문제 2개 — (user, problem) AC 중복을 피하기 위함
    with get_session() as s:
        p_old = create_problem(s, sample_problem, status="approved")
    with get_session() as s:
        p_new = create_problem(s, sample_problem, status="approved")

    only_old = make_user("only_old")
    both = make_user("both")

    sid_old_a = _ac_submission(only_old, p_old, points=300)
    sid_old_b = _ac_submission(both, p_old, points=300)
    # 두 사용자의 'p_old' AC는 지난 주로 백데이트
    last_week = datetime.now(timezone.utc) - timedelta(days=8)
    _backdate_submission(sid_old_a, last_week)
    _backdate_submission(sid_old_b, last_week)

    # 'both'만 이번 주에 p_new로 추가 AC
    _ac_submission(both, p_new, points=50)

    body = client.get("/leaderboard", params={"period": "week"}).json()
    ids = {e["user_id"]: e["points"] for e in body["entries"]}
    assert only_old not in ids  # 지난주 점수만 가짐
    assert ids.get(both) == 50  # 이번주에 얻은 50만 합산


def test_leaderboard_week_respects_limit(
    client: TestClient, make_user, sample_problem
):
    from src.storage.problems import create_problem

    users = [make_user(f"wk{i}") for i in range(4)]
    with get_session() as s:
        problems = [create_problem(s, sample_problem, status="approved") for _ in users]

    for u, p, pts in zip(users, problems, (40, 30, 20, 10)):
        _ac_submission(u, p, points=pts)

    body = client.get("/leaderboard", params={"period": "week", "limit": 2}).json()
    assert len(body["entries"]) == 2
    # 내림차순 points
    pts_seq = [e["points"] for e in body["entries"]]
    assert pts_seq == sorted(pts_seq, reverse=True)


def test_leaderboard_week_empty_when_no_submissions(client: TestClient):
    # 새 임시 DB로 테스트가 격리되진 않지만, 다른 테스트의 영향과 무관하게
    # 응답 구조와 week 라벨이 채워졌는지만 검증.
    body = client.get("/leaderboard", params={"period": "week"}).json()
    assert body["period"] == "week"
    assert body["week"] == iso_week_of(datetime.now(timezone.utc))
    assert isinstance(body["entries"], list)


def test_leaderboard_rejects_invalid_period(client: TestClient):
    r = client.get("/leaderboard", params={"period": "month"})
    assert r.status_code == 422


def test_leaderboard_rejects_limit_out_of_range(client: TestClient):
    assert client.get("/leaderboard", params={"limit": 0}).status_code == 422
    assert client.get("/leaderboard", params={"limit": 101}).status_code == 422
