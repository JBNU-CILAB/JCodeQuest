"""Code Battle(매일 20시 실시간 대전) 검증.

단위: 스코어보드 정렬, 베스트 캐시 갱신 규칙, 순위 보상/멱등, 배틀 exp 가드.
통합: 참가→제출→채점 done이 스코어보드에 반영되는지 (mock_engine으로 judge 대체).

배틀 격리: get_or_create_today_battle은 battle_date 유니크라 같은 DB(세션 스코프)에서
'오늘' 배틀을 공유한다. 테스트는 충돌·누적을 피하려고 연도 2000대의 고유 날짜로 배틀을
직접 만든다(_new_battle). 라우터는 저장된 status만 보므로 wall-clock 무관.
"""
from __future__ import annotations

import itertools
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from src.schemas import EnsembleResult, JudgeVote, TestResult
from src.storage import battles, get_session
from src.storage.models import BattleParticipantRow, BattleRow
from src.storage.submissions import create_submission, save_grading
from src.storage.users import get_user

# partial: n=3→6 ✓, n=0→0 ✓, n=-5→0 ✗(기대 -10) → 2/3 통과
PARTIAL_CODE = "n = int(input())\nprint(max(n * 2, 0))\n"
AC_CODE = "n = int(input())\nprint(n * 2)\n"

_date_seq = itertools.count(1)


def _fake_ac() -> EnsembleResult:
    return EnsembleResult(
        final_verdict="AC", mode="unanimous",
        votes=[
            JudgeVote(judge_id=jid, verdict="AC", intent_match=True,
                      rationale="ok", confidence=1.0)
            for jid in ("Melchior", "Balthasar", "Casper")
        ],
    )


def _new_battle(*, status: str = "active", problem_id: int | None = None) -> int:
    """테스트 격리용 — 연도 2000대 고유 날짜로 배틀 1판을 직접 만든다."""
    d = date(2000, 1, 1) + timedelta(days=next(_date_seq))
    lobby_at, start_at, end_at = battles.battle_window_for(d)
    with get_session() as s:
        b = BattleRow(
            battle_date=d, status=status, problem_id=problem_id,
            lobby_at=lobby_at, start_at=start_at, end_at=end_at,
        )
        s.add(b)
        s.commit()
        s.refresh(b)
        assert b.id is not None
        return b.id


def _add_participant(
    battle_id: int, user_id: int, *,
    is_ac: bool = False, tests_passed: int = 0, total: int = 3,
    best_at: datetime | None = None, attempts: int = 0,
) -> None:
    with get_session() as s:
        s.add(BattleParticipantRow(
            battle_id=battle_id, user_id=user_id, is_ac=is_ac,
            best_tests_passed=tests_passed, total_tests=total,
            best_at=best_at, attempts=attempts,
        ))
        s.commit()


# ───────────────────── 단위: 스코어보드 정렬 ─────────────────────
def test_scoreboard_ordering(make_user):
    bid = _new_battle()
    t0 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    a = make_user("A"); b = make_user("B"); c = make_user("C")
    d = make_user("D"); e = make_user("E")
    # AC-느림 / AC-빠름 / 부분2 / 부분1 / 미제출
    _add_participant(bid, a, is_ac=True, tests_passed=3, best_at=t0 + timedelta(seconds=10), attempts=2)
    _add_participant(bid, b, is_ac=True, tests_passed=3, best_at=t0 + timedelta(seconds=5), attempts=1)
    _add_participant(bid, c, is_ac=False, tests_passed=2, best_at=t0 + timedelta(seconds=3), attempts=3)
    _add_participant(bid, d, is_ac=False, tests_passed=1, best_at=t0 + timedelta(seconds=1), attempts=1)
    _add_participant(bid, e, is_ac=False, tests_passed=0, best_at=None, attempts=0)

    with get_session() as s:
        board = battles.compute_scoreboard(s, bid)

    order = [entry.user_id for entry in board]
    assert order == [b, a, c, d, e]  # AC-빠름 → AC-느림 → 부분2 → 부분1 → 미제출
    assert [entry.rank for entry in board] == [1, 2, 3, 4, 5]
    # solved_seconds = best_at - start_at, 미제출은 None
    assert board[-1].solved_seconds is None
    assert board[0].is_ac is True


# ───────────────────── 단위: 베스트 캐시 갱신 ─────────────────────
def _grade_battle_submission(
    user_id: int, problem_id: int, battle_id: int,
    *, passed: int, total: int, verdict: str,
) -> None:
    results = [TestResult(ordinal=i + 1, passed=(i < passed)) for i in range(total)]
    with get_session() as s:
        sid = create_submission(
            s, user_id=user_id, problem_id=problem_id, code="x", battle_id=battle_id,
        )
        save_grading(s, sid, final_verdict=verdict, test_results=results, points_awarded=0)
        battles.update_participant_from_submission(s, sid)


def test_best_only_improves(make_user, seeded_problem_id):
    bid = _new_battle(problem_id=seeded_problem_id)
    u = make_user("solver")
    battles_join(bid, u)

    # 부분 1/3 → AC 3/3 → 부분 2/3 (마지막은 AC보다 나쁘므로 무시돼야 함)
    _grade_battle_submission(u, seeded_problem_id, bid, passed=1, total=3, verdict="SUS")
    _grade_battle_submission(u, seeded_problem_id, bid, passed=3, total=3, verdict="AC")
    _grade_battle_submission(u, seeded_problem_id, bid, passed=2, total=3, verdict="SUS")

    with get_session() as s:
        part = battles.get_participant(s, bid, u)
        assert part is not None
        assert part.is_ac is True
        assert part.best_tests_passed == 3
        assert part.attempts == 3  # done 3건 모두 카운트


def battles_join(bid: int, user_id: int) -> None:
    with get_session() as s:
        battles.join_battle(s, bid, user_id)


# ───────────────────── 단위: exp 가드 ─────────────────────
def test_battle_submission_does_not_award_normal_exp(make_user, seeded_problem_id):
    normal_user = make_user("normal")
    battle_user = make_user("battler")
    bid = _new_battle(problem_id=seeded_problem_id)

    results = [TestResult(ordinal=i + 1, passed=True) for i in range(3)]
    with get_session() as s:
        # 일반 제출 AC → exp 가산
        sid_n = create_submission(s, user_id=normal_user, problem_id=seeded_problem_id, code="x")
        save_grading(s, sid_n, final_verdict="AC", test_results=results, points_awarded=100)
        # 배틀 제출 AC → exp 미가산(battle_id 가드)
        sid_b = create_submission(
            s, user_id=battle_user, problem_id=seeded_problem_id, code="x", battle_id=bid,
        )
        save_grading(s, sid_b, final_verdict="AC", test_results=results, points_awarded=100)

    with get_session() as s:
        assert get_user(s, normal_user).exp == 100
        assert get_user(s, battle_user).exp == 0


# ───────────────────── 단위: finalize 순위 보상/멱등 ─────────────────────
def test_finalize_assigns_ranks_and_rewards_idempotent(make_user, monkeypatch):
    monkeypatch.setattr(battles, "BATTLE_REWARD_TOP", [50, 30, 20])
    monkeypatch.setattr(battles, "BATTLE_PARTICIPATION_EXP", 5)
    bid = _new_battle(status="finished")
    t0 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    a = make_user("first"); b = make_user("second"); c = make_user("third")
    _add_participant(bid, a, is_ac=True, tests_passed=3, best_at=t0 + timedelta(seconds=5), attempts=1)
    _add_participant(bid, b, is_ac=True, tests_passed=3, best_at=t0 + timedelta(seconds=9), attempts=2)
    _add_participant(bid, c, is_ac=False, tests_passed=1, best_at=t0 + timedelta(seconds=2), attempts=1)

    with get_session() as s:
        board = battles.finalize_battle(s, bid)
    assert [e.user_id for e in board] == [a, b, c]

    with get_session() as s:
        assert get_user(s, a).exp == 50
        assert get_user(s, b).exp == 30
        assert get_user(s, c).exp == 20
        ranks = {
            p.user_id: p.rank
            for p in s.exec(
                select(BattleParticipantRow).where(
                    BattleParticipantRow.battle_id == bid
                )
            ).all()
        }
        assert ranks == {a: 1, b: 2, c: 3}

    # 재호출은 추가 가산 없음(멱등)
    with get_session() as s:
        battles.finalize_battle(s, bid)
    with get_session() as s:
        assert get_user(s, a).exp == 50
        assert get_user(s, b).exp == 30
        assert get_user(s, c).exp == 20


# ───────────────────── 단위: 타이밍 ─────────────────────
def test_battle_window_and_phase():
    d = date(2026, 5, 28)
    lobby_at, start_at, end_at = battles.battle_window_for(d)
    # 기본 20시 KST 시작, 로비 5분, 풀이 20분
    assert (start_at - lobby_at) == timedelta(minutes=battles.BATTLE_LOBBY_MIN)
    assert (end_at - start_at) == timedelta(minutes=battles.BATTLE_SOLVE_MIN)

    b = BattleRow(battle_date=d, status="scheduled",
                  lobby_at=lobby_at, start_at=start_at, end_at=end_at)
    assert battles.phase_for(b, lobby_at - timedelta(seconds=1)) == "scheduled"
    assert battles.phase_for(b, lobby_at + timedelta(seconds=1)) == "lobby"
    assert battles.phase_for(b, start_at + timedelta(seconds=1)) == "active"
    assert battles.phase_for(b, end_at + timedelta(seconds=1)) == "finished"


# ───────────────────── 단위: 상시 개방 모드 ─────────────────────
def test_ensure_always_open_idempotent_active(seeded_problem_id):
    """상시 개방: 오늘 배틀을 항상 active(문제 배정)로 유지하고 멱등."""
    bid = None
    try:
        with get_session() as s:
            b1 = battles.ensure_always_open(s)
            assert b1 is not None
            assert b1.status == "active"
            assert b1.problem_id is not None
            bid = b1.id
        with get_session() as s:
            b2 = battles.ensure_always_open(s)
            assert b2.id == bid  # 같은 '오늘' 배틀 (멱등)
            assert b2.status == "active"
    finally:
        # '오늘' 배틀은 세션 스코프 DB에 남아 test_current_no_battle을 오염시키므로 정리.
        if bid is not None:
            with get_session() as s:
                for p in s.exec(
                    select(BattleParticipantRow).where(
                        BattleParticipantRow.battle_id == bid
                    )
                ).all():
                    s.delete(p)
                row = s.get(BattleRow, bid)
                if row:
                    s.delete(row)
                s.commit()


# ───────────────────── 통합: 참가→제출→스코어보드 ─────────────────────
@pytest.fixture
def battle_client(monkeypatch, mock_engine):
    async def fake_vote(problem, code, test_results):
        return _fake_ac()
    mock_engine.set_vote(fake_vote)
    from src.main import app
    with TestClient(app) as c:
        yield c


def _wait_done(client: TestClient, sub_id: int, timeout_s: float = 10.0) -> dict:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        r = client.get(f"/grade/{sub_id}")
        assert r.status_code == 200
        if r.json()["status"] in ("done", "failed"):
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for submission {sub_id}")


def test_join_submit_reflected_in_scoreboard(battle_client, seeded_problem_id, login_as):
    bid = _new_battle(status="active", problem_id=seeded_problem_id)

    # user1: AC
    u1 = login_as(battle_client, email="u1@example.com", name="u1")
    assert battle_client.post(f"/battles/{bid}/join").status_code == 200
    r = battle_client.post(f"/battles/{bid}/submit", json={"code": AC_CODE})
    assert r.status_code == 202, r.text
    _wait_done(battle_client, r.json()["submission_id"])

    # user2: 부분(2/3)
    battle_client.cookies.clear()
    u2 = login_as(battle_client, email="u2@example.com", name="u2")
    assert battle_client.post(f"/battles/{bid}/join").status_code == 200
    r = battle_client.post(f"/battles/{bid}/submit", json={"code": PARTIAL_CODE})
    assert r.status_code == 202, r.text
    _wait_done(battle_client, r.json()["submission_id"])

    snap = battle_client.get(f"/battles/{bid}").json()
    assert snap["status"] == "active"
    assert snap["participant_count"] == 2
    by_user = {e["user_id"]: e for e in snap["scoreboard"]}
    assert by_user[u1]["rank"] == 1
    assert by_user[u1]["is_ac"] is True and by_user[u1]["tests_passed"] == 3
    assert by_user[u2]["rank"] == 2
    assert by_user[u2]["is_ac"] is False and by_user[u2]["tests_passed"] == 2
    # 인증 REST는 my_rank/joined를 채운다 (마지막 요청자 = u2)
    assert snap["joined"] is True and snap["my_rank"] == 2


def test_submit_requires_active_phase(battle_client, seeded_problem_id, login_as):
    bid = _new_battle(status="lobby", problem_id=seeded_problem_id)
    login_as(battle_client, email="lob@example.com", name="lob")
    r = battle_client.post(f"/battles/{bid}/submit", json={"code": AC_CODE})
    assert r.status_code == 409


def test_join_rejected_after_finished(battle_client, login_as):
    bid = _new_battle(status="finished")
    login_as(battle_client, email="fin@example.com", name="fin")
    assert battle_client.post(f"/battles/{bid}/join").status_code == 409


def test_current_returns_next_start_when_no_battle(battle_client, login_as):
    # 테스트는 연도 2000대 날짜만 쓰므로 '오늘'(KST) 배틀은 없다.
    login_as(battle_client, email="cur@example.com", name="cur")
    snap = battle_client.get("/battles/current").json()
    assert snap["status"] is None
    assert snap["battle_id"] is None
    assert snap["next_start_at"] is not None
