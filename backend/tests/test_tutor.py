"""POST /tutor/{submission_id} 흐름 검증.

OpenAI API는 monkeypatch로 mocking — 외부 의존 제거.
같은 conftest의 임시 SQLite + 쿠다운 0 fixture를 그대로 재사용한다."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from src.schemas import EnsembleResult, JudgeVote


def _ac_ensemble() -> EnsembleResult:
    return EnsembleResult(
        final_verdict="AC",
        mode="unanimous",
        votes=[
            JudgeVote(
                judge_id=jid,
                verdict="AC",
                intent_match=True,
                rationale=f"{jid} 이유",
                confidence=1.0,
            )
            for jid in ("Melchior", "Balthasar", "Casper")
        ],
    )


@pytest.fixture
def client(monkeypatch):
    # 채점 단계의 LLM은 mocking — 모든 통과 시나리오에서 AC ensemble 반환
    async def fake_vote(problem, code, test_results, base_url=None):
        return _ac_ensemble()

    import src.judge.jobs.grading as grading_mod
    monkeypatch.setattr(grading_mod, "vote", fake_vote)

    from src.main import app
    with TestClient(app) as c:
        yield c


def _wait_done(c: TestClient, sub_id: int, timeout_s: float = 10.0) -> dict:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        body = c.get(f"/grade/{sub_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {sub_id}")


def _create_done_submission(
    c: TestClient,
    problem_id: int,
    *,
    user_id: int = 1,
    code: str = "n = int(input())\nprint(n * 2)\n",
) -> int:
    r = c.post("/grade", json={"user_id": user_id, "problem_id": problem_id, "code": code})
    assert r.status_code == 202, r.text
    sid = r.json()["submission_id"]
    body = _wait_done(c, sid)
    assert body["status"] == "done"
    return sid


# ────────────────────────── 라우터 happy / 에러 ──────────────────────────


def test_tutor_returns_message_for_ac(
    client: TestClient, seeded_problem_id: int, monkeypatch
):
    captured: dict = {}

    async def fake_tutor(*, problem, code, verdict, votes, test_results):
        captured.update(
            problem=problem, code=code, verdict=verdict,
            votes=votes, test_results=test_results,
        )
        return "잘했어요. 더 깔끔하게 짤 수 있어요.", "gpt-4o-mini"

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", fake_tutor)

    sid = _create_done_submission(client, seeded_problem_id, user_id=11)
    r = client.post(f"/tutor/{sid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "submission_id": sid,
        "message": "잘했어요. 더 깔끔하게 짤 수 있어요.",
    }

    # tutor에 넘어간 context 검증
    assert captured["verdict"] == "AC"
    assert captured["votes"] is not None and len(captured["votes"]) == 3
    judge_ids = {v["judge_id"] for v in captured["votes"]}
    assert judge_ids == {"Melchior", "Balthasar", "Casper"}
    assert captured["problem"].title == "2배 출력"
    assert "n * 2" in captured["code"]
    assert len(captured["test_results"]) == 3


def test_tutor_when_sandbox_fail_no_votes(
    client: TestClient, seeded_problem_id: int, monkeypatch
):
    """WA로 끝난 제출(LLM 미호출 → votes=None)도 튜터링 가능해야."""
    captured: dict = {}

    async def fake_tutor(**kwargs):
        captured.update(kwargs)
        return "출력 식을 다시 살펴보세요.", "gpt-4o-mini"

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", fake_tutor)

    sid = _create_done_submission(
        client, seeded_problem_id, user_id=12,
        code="n = int(input())\nprint(n + 1)\n",  # 오답
    )
    r = client.post(f"/tutor/{sid}")
    assert r.status_code == 200, r.text
    assert captured["votes"] is None
    assert captured["verdict"] == "SUS"
    # WA 케이스 결과가 그대로 넘어왔는지
    assert any(not t.get("passed") for t in captured["test_results"])


def test_tutor_404_on_missing_submission(client: TestClient, monkeypatch):
    async def boom(**_kwargs):
        raise AssertionError("OpenAI는 호출되면 안 됨")

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", boom)

    r = client.post("/tutor/999999")
    assert r.status_code == 404


def test_tutor_409_when_submission_not_done(
    client: TestClient, seeded_problem_id: int, monkeypatch
):
    """status=queued 상태(=채점 안 끝남)에 호출하면 409."""
    from src.storage import get_session
    from src.storage.submissions import create_submission

    # 큐를 거치지 않고 직접 row 삽입 → status 기본값은 "queued"
    with get_session() as s:
        sid = create_submission(s, user_id=66, problem_id=seeded_problem_id, code="x")

    async def boom(**_kwargs):
        raise AssertionError("OpenAI는 호출되면 안 됨")

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", boom)

    r = client.post(f"/tutor/{sid}")
    assert r.status_code == 409
    assert "queued" in r.json()["detail"]


# ────────────────────────── 프롬프트 렌더링 ──────────────────────────


def test_render_user_message_includes_all_sections(sample_problem):
    from src.tutor.prompts import render_user_message

    msg = render_user_message(
        problem=sample_problem,
        code="print('hi')",
        verdict="SUS",
        votes=[
            {
                "judge_id": "Melchior",
                "verdict": "SUS",
                "intent_match": False,
                "confidence": 0.9,
                "rationale": "하드코딩 의심",
            },
        ],
        test_results=[
            {"ordinal": 1, "passed": True, "status": "OK", "elapsed_ms": 10},
            {
                "ordinal": 2, "passed": False, "status": "OK",
                "actual_stdout": "x", "elapsed_ms": 12,
            },
            {
                "ordinal": 3, "passed": False, "status": "RE",
                "error": "ZeroDivisionError: division by zero",
            },
        ],
    )
    assert "[문제]" in msg
    assert "[출제자 의도]" in msg
    assert "print('hi')" in msg
    assert "[테스트 결과] 1/3 통과" in msg
    assert "ZeroDivisionError" in msg
    assert "[판사 의견]" in msg
    assert "Melchior" in msg
    assert "[최종 판정] SUS" in msg


def test_render_user_message_skips_votes_when_none(sample_problem):
    from src.tutor.prompts import render_user_message

    msg = render_user_message(
        problem=sample_problem,
        code="x",
        verdict="SUS",
        votes=None,
        test_results=[
            {"ordinal": 1, "passed": False, "status": "TLE"},
        ],
    )
    assert "[판사 의견]" not in msg
    assert "[최종 판정] SUS" in msg
    assert "TLE" in msg
