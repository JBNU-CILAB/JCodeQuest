"""first-AC plagiarism 자동 트리거 훅 — apply_grading_event 의 반환 계약과
/internal/grade-events webhook 이 notify_first_ac 를 정확히 호출하는지 검증.

플랜:
1. apply_grading_event 가 첫 AC(비배틀) → submission_id, 후속 AC → None,
   running/failed → None 을 돌려주는지.
2. /internal/grade-events 가 첫 AC 인 경우만 notify_first_ac 를 호출하는지 (monkeypatch 카운트).
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from jcq_shared.schemas import EnsembleResult, JudgeVote

from src.judge.jobs import apply_grading_event
from src.schemas import GradeEvent, TestResult
from src.storage import get_session
from src.storage.submissions import create_submission


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


def _ac_event(submission_id: int) -> GradeEvent:
    """전 테스트 AC + 앙상블 만장일치 AC 인 done 이벤트."""
    return GradeEvent(
        submission_id=submission_id,
        event="done",
        test_results=[TestResult(
            ordinal=1, stdin="1", expected_stdout="1", actual_stdout="1",
            passed=True, elapsed_ms=1, peak_memory_kb=1,
        )],
        all_passed=True,
        ensemble=EnsembleResult(
            mode="unanimous",
            final_verdict="AC",
            votes=[
                JudgeVote(judge_id="Melchior",  verdict="AC", intent_match=True, rationale="ok", confidence=0.95),
                JudgeVote(judge_id="Balthasar", verdict="AC", intent_match=True, rationale="ok", confidence=0.92),
                JudgeVote(judge_id="Casper",    verdict="AC", intent_match=True, rationale="ok", confidence=0.90),
            ],
        ),
    )


def test_apply_grading_event_returns_sid_for_first_ac_then_none(seeded_problem_id, make_user):
    """첫 AC → submission_id, 후속 AC → None."""
    pid, uid = seeded_problem_id, make_user()

    with get_session() as s:
        first_sid = create_submission(s, user_id=uid, problem_id=pid, code="print(input())")
    rv1 = apply_grading_event(_ac_event(first_sid))
    assert rv1 == first_sid, "첫 AC 는 submission_id 를 반환해야 함"

    with get_session() as s:
        second_sid = create_submission(s, user_id=uid, problem_id=pid, code="print(input())")
    rv2 = apply_grading_event(_ac_event(second_sid))
    assert rv2 is None, "이미 AC 한 문제의 추가 AC 는 None"


def test_apply_grading_event_returns_none_for_running_and_failed(seeded_problem_id, make_user):
    pid, uid = seeded_problem_id, make_user()
    with get_session() as s:
        sid = create_submission(s, user_id=uid, problem_id=pid, code="print(input())")

    assert apply_grading_event(GradeEvent(submission_id=sid, event="running")) is None
    assert (
        apply_grading_event(GradeEvent(submission_id=sid, event="failed", error="x"))
        is None
    )


def test_webhook_invokes_plagiarism_notify_only_on_first_ac(client, monkeypatch, seeded_problem_id, make_user):
    """/internal/grade-events 가 첫 AC 시 notify_first_ac 호출, 후속 AC 는 호출 안 함."""
    pid, uid = seeded_problem_id, make_user()

    # notify_first_ac 는 webhook 핸들러가 함수 안에서 import — 그 import 결과(`pc.notify_first_ac`)를
    # 가짜로 교체. monkeypatch 가 자동으로 원복.
    notify = AsyncMock()
    import src.plagiarism_client as pc

    monkeypatch.setattr(pc, "notify_first_ac", notify)

    with get_session() as s:
        first_sid = create_submission(s, user_id=uid, problem_id=pid, code="print(input())")
    r = client.post(
        "/internal/grade-events",
        headers=_auth(),
        json=_ac_event(first_sid).model_dump(),
    )
    assert r.status_code == 200, r.text
    notify.assert_awaited_once_with(first_sid)

    notify.reset_mock()
    with get_session() as s:
        second_sid = create_submission(s, user_id=uid, problem_id=pid, code="print(input())")
    r2 = client.post(
        "/internal/grade-events",
        headers=_auth(),
        json=_ac_event(second_sid).model_dump(),
    )
    assert r2.status_code == 200, r2.text
    notify.assert_not_awaited()
