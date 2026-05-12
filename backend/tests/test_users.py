"""User 모델/헬퍼 + save_grading의 exp 가산 hook 검증."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from src.schemas import EnsembleResult, JudgeVote, TestResult
from src.storage import get_session
from src.storage.submissions import create_submission, save_grading
from src.storage.users import bump_user_exp, get_or_create_user, get_user


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


def _sus_ensemble() -> EnsembleResult:
    return EnsembleResult(
        final_verdict="SUS",
        mode="unanimous",
        votes=[
            JudgeVote(
                judge_id=jid, verdict="SUS", intent_match=False,
                rationale="hardcoded", confidence=0.9,
            )
            for jid in ("Melchior", "Balthasar", "Casper")
        ],
    )


def _ok_results() -> list[TestResult]:
    return [
        TestResult(ordinal=1, passed=True, status="OK", elapsed_ms=10, peak_memory_kb=8000),
        TestResult(ordinal=2, passed=True, status="OK", elapsed_ms=12, peak_memory_kb=8200),
    ]


# ───────────────────────── helpers ─────────────────────────


def test_get_or_create_user_idempotent_on_provider_sub():
    with get_session() as s:
        a = get_or_create_user(
            s, provider="dev_stub", external_id="dup-1",
            display_name="원본", email="x@example.com",
        )
        b = get_or_create_user(
            s, provider="dev_stub", external_id="dup-1",
            display_name="다른이름",  # 기존 행이 그대로 반환되어야 — 갱신 X
        )
        # 세션 detach 전에 비교에 필요한 값만 빼냄
        a_id, b_id = a.id, b.id
        b_name, b_email = b.display_name, b.email
    assert a_id == b_id
    assert b_name == "원본"
    assert b_email == "x@example.com"


def test_get_or_create_user_distinct_per_provider():
    """같은 external_id라도 provider가 다르면 별개 사용자."""
    with get_session() as s:
        a = get_or_create_user(
            s, provider="dev_stub", external_id="shared-id", display_name="A",
        )
        b = get_or_create_user(
            s, provider="school_sso", external_id="shared-id", display_name="B",
        )
        a_id, b_id = a.id, b.id
    assert a_id != b_id


def test_bump_user_exp_increments_and_touches_updated_at(make_user):
    user_id = make_user()
    with get_session() as s:
        before = get_user(s, user_id)
        assert before is not None
        before_exp = before.exp
        before_updated = before.updated_at

    with get_session() as s:
        bump_user_exp(s, user_id, delta=42)
        s.commit()
        after = get_user(s, user_id)

    assert after is not None
    assert after.exp == before_exp + 42
    assert after.updated_at >= before_updated


def test_bump_user_exp_noop_on_zero_or_negative(make_user):
    user_id = make_user()
    with get_session() as s:
        bump_user_exp(s, user_id, delta=0)
        bump_user_exp(s, user_id, delta=-5)
        s.commit()
        u = get_user(s, user_id)
    assert u is not None
    assert u.exp == 0


# ───────────────────────── FK enforcement ─────────────────────────


def test_submission_rejects_unknown_user(seeded_problem_id):
    """SubmissionRow.user_id는 user.id FK — 존재하지 않는 user_id는 IntegrityError."""
    with pytest.raises(IntegrityError):
        with get_session() as s:
            create_submission(
                s, user_id=999_999_999, problem_id=seeded_problem_id, code="x",
            )


# ───────────────────────── save_grading exp hook ─────────────────────────


def test_save_grading_ac_bumps_exp_once(seeded_problem_id, make_user):
    user_id = make_user()
    with get_session() as s:
        sid = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="ok",
        )
        save_grading(
            s, sid,
            final_verdict="AC",
            test_results=_ok_results(),
            ensemble=_ac_ensemble(),
            points_awarded=87,
        )
        u = get_user(s, user_id)
    assert u is not None
    assert u.exp == 87


def test_save_grading_sus_does_not_bump_exp(seeded_problem_id, make_user):
    user_id = make_user()
    with get_session() as s:
        sid = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="bad",
        )
        save_grading(
            s, sid,
            final_verdict="SUS",
            test_results=_ok_results(),
            ensemble=_sus_ensemble(),
            points_awarded=0,
        )
        u = get_user(s, user_id)
    assert u is not None
    assert u.exp == 0


def test_save_grading_second_ac_does_not_double_bump(seeded_problem_id, make_user):
    """방어적 — POST /grade는 solved 시 409로 막지만, save_grading 직접 호출이라도
    같은 (user, problem)의 두 번째 AC는 가산하지 않아야 함."""
    user_id = make_user()
    with get_session() as s:
        sid1 = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="ok1",
        )
        save_grading(
            s, sid1,
            final_verdict="AC",
            test_results=_ok_results(),
            ensemble=_ac_ensemble(),
            points_awarded=100,
        )
        sid2 = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="ok2",
        )
        save_grading(
            s, sid2,
            final_verdict="AC",
            test_results=_ok_results(),
            ensemble=_ac_ensemble(),
            points_awarded=100,
        )
        u = get_user(s, user_id)
    assert u is not None
    assert u.exp == 100  # 두 번째는 가산 안됨
