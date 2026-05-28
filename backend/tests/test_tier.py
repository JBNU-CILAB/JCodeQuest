"""4단계 티어 산정 + 자동 갱신 검사.

산식:
    임계 % (기본): amateur=10, professional=30, master=60 of max_exp
    max_exp = approved 문제들의 points 합

자동 갱신 지점:
    - bump_user_exp(): exp가 오르며 임계를 넘으면 UserRow.tier가 따라 바뀐다.
    - create_problem(approved) / update_problem(status·points) / delete_problem(approved):
      max_exp가 흔들리면 전체 사용자가 재계산된다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.schemas import IntentRubric, Problem, TestCase
from src.storage import get_session
from src.storage.models import ProblemRow, UserRow
from src.storage.problems import create_problem, delete_problem, update_problem
from src.storage.users import bump_user_exp
from src.tier import (
    TIER_ORDER,
    compute_tier,
    get_max_exp,
    recompute_all_tiers,
    tier_progress,
)


# ───────────────────────── 단위: compute_tier ─────────────────────────


def test_compute_tier_zero_max_exp_is_beginner():
    # 승인 문제 없으면 누구나 beginner — 0/0 분모 회피.
    assert compute_tier(0, 0) == "beginner"
    assert compute_tier(9999, 0) == "beginner"


def test_compute_tier_thresholds_default():
    # 기본 임계: 10% amateur, 30% professional, 60% master. max_exp=1000 기준 환산.
    assert compute_tier(0, 1000) == "beginner"
    assert compute_tier(99, 1000) == "beginner"     # 9.9%
    assert compute_tier(100, 1000) == "amateur"     # 10% 정확히
    assert compute_tier(299, 1000) == "amateur"     # 29.9%
    assert compute_tier(300, 1000) == "professional"
    assert compute_tier(599, 1000) == "professional"
    assert compute_tier(600, 1000) == "master"
    assert compute_tier(10_000, 1000) == "master"   # 100% 초과도 master


def test_compute_tier_override_via_env(monkeypatch):
    # 환경변수가 우선. 잘못 뒤집힌 입력도 정렬해서 안전하게 적용된다.
    monkeypatch.setenv("JCQ_TIER_AMATEUR_PCT", "50")
    monkeypatch.setenv("JCQ_TIER_PROFESSIONAL_PCT", "70")
    monkeypatch.setenv("JCQ_TIER_MASTER_PCT", "90")
    assert compute_tier(400, 1000) == "beginner"
    assert compute_tier(500, 1000) == "amateur"
    assert compute_tier(700, 1000) == "professional"
    assert compute_tier(900, 1000) == "master"


# ───────────────────────── 단위: tier_progress ─────────────────────────


def test_tier_progress_master_caps_at_100():
    # master 진입 후엔 다음 티어가 없으므로 next=None, progress_pct=100 고정.
    p = tier_progress(800, 1000)
    assert p.current == "master"
    assert p.next is None
    assert p.exp_to_next == 0
    assert p.progress_pct == 100.0


def test_tier_progress_within_band_is_linear():
    # amateur 구간(100~300)의 중간 200 → 50%.
    p = tier_progress(200, 1000)
    assert p.current == "amateur"
    assert p.next == "professional"
    assert p.exp_to_next == 100
    assert 49.0 <= p.progress_pct <= 51.0


def test_tier_progress_beginner_at_zero():
    p = tier_progress(0, 1000)
    assert p.current == "beginner"
    assert p.next == "amateur"
    assert p.exp_to_next == 100  # 다음 컷이 10% = 100


def test_tier_progress_empty_system():
    # 승인 문제가 하나도 없으면 진행도는 0%, current=beginner.
    p = tier_progress(0, 0)
    assert p.current == "beginner"
    assert p.progress_pct == 0.0
    assert p.max_exp == 0


def test_tier_order_is_low_to_high():
    # API/프론트가 순서를 그대로 가정하므로 변경되면 문서 동기화 필요.
    assert TIER_ORDER == ("beginner", "amateur", "professional", "master")


# ───────────────────────── 통합: bump_user_exp + tier 갱신 ─────────────────────────


def _seed_problem(points: int) -> int:
    p = Problem(
        id=0,
        title=f"문제 {points}",
        statement="x",
        category="basic",
        level="bronze",
        points=points,
        time_limit_ms=1000,
        memory_limit_mb=128,
        reference_code="print(1)\n",
        intent_rubric=IntentRubric(
            expected_approach="x",
            expected_complexity="O(1)",
            must_handle=[],
            forbidden_patterns=[],
            key_insight="x",
            one_line_summary="x",
        ),
        test_cases=[
            TestCase(ordinal=1, stdin="", expected_stdout="1", is_sample=True),
        ],
    )
    with get_session() as s:
        return create_problem(s, p, status="approved")


def test_bump_user_exp_promotes_tier_inline(make_user):
    # 200 points짜리 문제 → 10%=20 EXP에서 amateur, 60%=120에서 master.
    _seed_problem(200)
    uid = make_user()
    with get_session() as s:
        bump_user_exp(s, uid, delta=20)
        s.commit()
        u = s.get(UserRow, uid)
        assert u is not None
        assert u.tier == "amateur"
    with get_session() as s:
        bump_user_exp(s, uid, delta=100)  # 누적 120 = 60%
        s.commit()
        u = s.get(UserRow, uid)
        assert u is not None
        assert u.tier == "master"


# ───────────────────────── 통합: max_exp 변동 시 전체 재계산 ─────────────────────────


def test_creating_approved_problem_demotes_users(make_user):
    # max_exp=100, exp=60 → master. 새 문제가 100점 더 들어와서 max_exp=200 되면 60/200=30% → professional.
    _seed_problem(100)
    uid = make_user()
    with get_session() as s:
        bump_user_exp(s, uid, delta=60)
        s.commit()
        assert s.get(UserRow, uid).tier == "master"

    _seed_problem(100)
    with get_session() as s:
        u = s.get(UserRow, uid)
        assert u is not None
        # 60/200 = 30% 정확히 → professional 컷에 걸린다.
        assert u.tier == "professional"


def test_deleting_approved_problem_promotes_users(make_user):
    # 100점 두 개로 시작해서 60점 쌓고, 한 개 삭제하면 max_exp가 줄어 60/100=60%=master.
    pid_keep = _seed_problem(100)
    pid_drop = _seed_problem(100)
    assert pid_keep != pid_drop
    uid = make_user()
    with get_session() as s:
        bump_user_exp(s, uid, delta=60)
        s.commit()
        assert s.get(UserRow, uid).tier == "professional"

    with get_session() as s:
        assert delete_problem(s, pid_drop) is not None
    with get_session() as s:
        u = s.get(UserRow, uid)
        assert u is not None
        assert u.tier == "master"


def test_draft_problem_does_not_shift_thresholds(make_user):
    # draft 상태로 만든 문제는 max_exp에 들어가지 않으므로 기존 사용자의 티어가 흔들리지 않는다.
    _seed_problem(100)
    uid = make_user()
    with get_session() as s:
        bump_user_exp(s, uid, delta=60)
        s.commit()
        assert s.get(UserRow, uid).tier == "master"

    # draft로 새 문제 생성.
    draft = Problem(
        id=0,
        title="draft",
        statement="x",
        category="basic",
        level="bronze",
        points=10_000,
        time_limit_ms=1000,
        memory_limit_mb=128,
        reference_code="print(1)\n",
        intent_rubric=IntentRubric(
            expected_approach="x",
            expected_complexity="O(1)",
            must_handle=[],
            forbidden_patterns=[],
            key_insight="x",
            one_line_summary="x",
        ),
        test_cases=[
            TestCase(ordinal=1, stdin="", expected_stdout="1", is_sample=True),
        ],
    )
    with get_session() as s:
        create_problem(s, draft, status="draft")

    with get_session() as s:
        # max_exp는 그대로 100. 사용자 티어 미변동.
        assert get_max_exp(s) == 100
        assert s.get(UserRow, uid).tier == "master"


def test_update_problem_status_to_approved_triggers_recompute(make_user):
    # 처음엔 draft였다가 approved로 승격되면 max_exp가 늘어 모든 사용자 재계산.
    _seed_problem(100)
    uid = make_user()
    with get_session() as s:
        bump_user_exp(s, uid, delta=60)
        s.commit()
        assert s.get(UserRow, uid).tier == "master"

    # draft 문제를 만들고 → approved로 변경.
    draft = Problem(
        id=0,
        title="late approve",
        statement="x",
        category="basic",
        level="bronze",
        points=100,
        time_limit_ms=1000,
        memory_limit_mb=128,
        reference_code="print(1)\n",
        intent_rubric=IntentRubric(
            expected_approach="x",
            expected_complexity="O(1)",
            must_handle=[],
            forbidden_patterns=[],
            key_insight="x",
            one_line_summary="x",
        ),
        test_cases=[
            TestCase(ordinal=1, stdin="", expected_stdout="1", is_sample=True),
        ],
    )
    with get_session() as s:
        new_pid = create_problem(s, draft, status="draft")
        # draft 단계: 영향 없음.
        assert s.get(UserRow, uid).tier == "master"
    with get_session() as s:
        update_problem(s, new_pid, fields={"status": "approved"})
    with get_session() as s:
        u = s.get(UserRow, uid)
        assert u is not None
        # max_exp=200 으로 늘어 60/200=30% → professional.
        assert u.tier == "professional"


def test_recompute_all_tiers_is_idempotent(make_user):
    _seed_problem(100)
    uid = make_user()
    with get_session() as s:
        bump_user_exp(s, uid, delta=60)
        s.commit()
        before = s.get(UserRow, uid).tier
        changed = recompute_all_tiers(s)
        assert changed == 0
        assert s.get(UserRow, uid).tier == before


# ───────────────────────── API: /me 응답에 tier_progress 포함 ─────────────────────────


@pytest.fixture
def client():
    from src.main import app
    with TestClient(app) as c:
        yield c


def test_me_response_carries_tier_progress(client: TestClient, login_as):
    _seed_problem(200)
    uid = login_as(client, email="tieruser@example.com", name="tier user")
    with get_session() as s:
        bump_user_exp(s, uid, delta=40)  # 20%
        s.commit()
    r = client.get("/me")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] == "amateur"
    progress = body["tier_progress"]
    assert progress is not None
    assert progress["current"] == "amateur"
    assert progress["next"] == "professional"
    assert progress["max_exp"] == 200
    assert progress["exp_to_next"] == 20  # 30% 컷 = 60 → 남은 20


def test_public_profile_includes_tier_progress(client: TestClient, login_as, make_user):
    _seed_problem(200)
    uid = make_user()
    with get_session() as s:
        bump_user_exp(s, uid, delta=120)  # 60%
        s.commit()
    r = client.get(f"/users/{uid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] == "master"
    progress = body["tier_progress"]
    assert progress is not None
    assert progress["current"] == "master"
    assert progress["next"] is None
    assert progress["progress_pct"] == 100.0


def teardown_function() -> None:
    # 한 테스트가 max_exp를 늘려 둔 상태로 다음 테스트에 새는 걸 방지.
    # 함수 단위로 ProblemRow를 청소 — UserRow는 fixture가 매번 새로 만든다.
    with get_session() as s:
        for row in list(s.exec(__import__("sqlmodel").select(ProblemRow)).all()):
            s.delete(row)
        s.commit()
        # 문제 다 비웠으니 max_exp=0 — 잔존 사용자들도 beginner로 정규화.
        recompute_all_tiers(s)
