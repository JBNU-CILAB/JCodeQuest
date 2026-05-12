from src.schemas import EnsembleResult, JudgeVote, Problem, TestResult
from src.storage import get_session
from src.storage.models import ProblemRow
from src.storage.problems import create_problem, get_problem
from src.storage.submissions import (
    MAX_ATTEMPTS,
    attempt_status,
    create_submission,
    get_submission,
    save_grading,
)


def _ac_ensemble() -> EnsembleResult:
    votes = [
        JudgeVote(
            judge_id=jid,
            verdict="AC",
            intent_match=True,
            rationale="ok",
            confidence=1.0,
        )
        for jid in ("Melchior", "Balthasar", "Casper")
    ]
    return EnsembleResult(final_verdict="AC", mode="unanimous", votes=votes)


def _sus_ensemble() -> EnsembleResult:
    votes = [
        JudgeVote(
            judge_id=jid,
            verdict="SUS",
            intent_match=False,
            rationale="hardcoded",
            confidence=0.9,
        )
        for jid in ("Melchior", "Balthasar", "Casper")
    ]
    return EnsembleResult(final_verdict="SUS", mode="unanimous", votes=votes)


def _ok_results() -> list[TestResult]:
    return [
        TestResult(ordinal=1, passed=True, status="OK", elapsed_ms=10, peak_memory_kb=8000),
        TestResult(ordinal=2, passed=True, status="OK", elapsed_ms=12, peak_memory_kb=8200),
    ]


def test_problem_roundtrip(seeded_problem_id: int):
    with get_session() as s:
        p = get_problem(s, seeded_problem_id)
    assert p is not None
    assert p.title == "2배 출력"
    assert len(p.test_cases) == 3
    assert p.time_limit_ms == 1000
    assert p.memory_limit_mb == 128
    assert p.intent_rubric.expected_complexity == "O(1)"


def test_attempt_count_only_llm_judged(seeded_problem_id: int, make_user):
    """테스트 실패(test-fail SUS, mode=None)는 시도 카운트에서 제외돼야 한다."""
    user_id = make_user()
    with get_session() as s:
        # 1) 테스트 실패: ensemble=None, final_verdict="SUS"
        sid1 = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="bad"
        )
        save_grading(
            s, sid1,
            final_verdict="SUS",
            test_results=[TestResult(ordinal=1, passed=False, status="OK")],
            ensemble=None,
            points_awarded=0,
        )
        st = attempt_status(s, user_id, seeded_problem_id)
    assert st.attempts == 0  # test-fail은 안 세어짐
    assert st.solved is False

    # 2) LLM-judge SUS: mode 채워짐
    with get_session() as s:
        sid2 = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="suspicious"
        )
        save_grading(
            s, sid2,
            final_verdict="SUS",
            test_results=_ok_results(),
            ensemble=_sus_ensemble(),
            points_awarded=0,
        )
        st = attempt_status(s, user_id, seeded_problem_id)
    assert st.attempts == 1
    assert st.solved is False
    assert st.remaining == MAX_ATTEMPTS - 1


def test_ac_locks_out(seeded_problem_id: int, make_user):
    user_id = make_user()
    with get_session() as s:
        sid = create_submission(
            s, user_id=user_id, problem_id=seeded_problem_id, code="good"
        )
        save_grading(
            s, sid,
            final_verdict="AC",
            test_results=_ok_results(),
            ensemble=_ac_ensemble(),
            points_awarded=100,
        )
        st = attempt_status(s, user_id, seeded_problem_id)
        sub = get_submission(s, sid)
    assert st.solved is True
    assert st.can_submit is False
    assert sub is not None
    assert sub.status == "done"
    assert sub.points_awarded == 100


def test_create_problem_uses_default_iso_week(sample_problem: Problem):
    """iso_week를 명시하지 않으면 default_factory가 '지금 주차'를 박는다."""
    from datetime import datetime, timezone

    from src.storage.models import iso_week_of

    with get_session() as s:
        pid = create_problem(s, sample_problem, status="approved")
        row = s.get(ProblemRow, pid)
    assert row is not None
    assert row.iso_week == iso_week_of(datetime.now(timezone.utc))


def test_create_problem_honors_explicit_iso_week(sample_problem: Problem):
    """출제 엔진처럼 호출자가 명시한 주차는 그대로 저장된다."""
    with get_session() as s:
        pid = create_problem(
            s, sample_problem, status="approved", iso_week="2024-W42"
        )
        row = s.get(ProblemRow, pid)
    assert row is not None
    assert row.iso_week == "2024-W42"
