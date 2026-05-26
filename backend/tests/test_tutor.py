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
def client(mock_engine):
    # 채점 단계의 LLM은 mocking — 모든 통과 시나리오에서 AC ensemble 반환
    async def fake_vote(problem, code, test_results):
        return _ac_ensemble()

    mock_engine.set_vote(fake_vote)

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
    email: str,
    code: str = "n = int(input())\nprint(n * 2)\n",
) -> int:
    """email로 dev-login한 뒤 /grade에 제출 → done까지 대기. 기존 쿠키는 클리어."""
    c.cookies.clear()
    r_login = c.post("/auth/dev-login", params={"email": email})
    assert r_login.status_code == 200, r_login.text
    r = c.post("/grade", json={"problem_id": problem_id, "code": code})
    assert r.status_code == 202, r.text
    sid = r.json()["submission_id"]
    body = _wait_done(c, sid)
    assert body["status"] == "done"
    return sid


def _set_api_key(c: TestClient, api_key: str = "test-api-key-with-20-chars") -> None:
    """현재 세션 사용자에게 API 키를 설정한다."""
    r = c.put("/me/api-key", json={"api_key": api_key})
    assert r.status_code == 200, r.text


# ────────────────────────── 라우터 happy / 에러 ──────────────────────────


def test_tutor_returns_message_for_ac(
    client: TestClient, seeded_problem_id: int, monkeypatch, make_user
):
    captured: dict = {}

    async def fake_tutor(*, problem, code, verdict, votes, test_results, api_key):
        captured.update(
            problem=problem, code=code, verdict=verdict,
            votes=votes, test_results=test_results, api_key=api_key,
        )
        return "잘했어요. 더 깔끔하게 짤 수 있어요.", "gpt-4o-mini"

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", fake_tutor)

    sid = _create_done_submission(client, seeded_problem_id, email="ac@example.com")
    _set_api_key(client)
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
    # 사용자가 등록한 키가 그대로 LLM 호출까지 전달돼야 한다(서버 전역 키 아님).
    assert captured["api_key"] == "test-api-key-with-20-chars"


def test_tutor_when_sandbox_fail_no_votes(
    client: TestClient, seeded_problem_id: int, monkeypatch, make_user
):
    """WA로 끝난 제출(LLM 미호출 → votes=None)도 튜터링 가능해야."""
    captured: dict = {}

    async def fake_tutor(**kwargs):
        captured.update(kwargs)
        return "출력 식을 다시 살펴보세요.", "gpt-4o-mini"

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", fake_tutor)

    sid = _create_done_submission(
        client, seeded_problem_id, email="wa@example.com",
        code="n = int(input())\nprint(n + 1)\n",  # 오답
    )
    _set_api_key(client)
    r = client.post(f"/tutor/{sid}")
    assert r.status_code == 200, r.text
    assert captured["votes"] is None
    assert captured["verdict"] == "SUS"
    # WA 케이스 결과가 그대로 넘어왔는지
    assert any(not t.get("passed") for t in captured["test_results"])


def test_tutor_caches_by_default(
    client: TestClient, seeded_problem_id: int, monkeypatch, make_user
):
    """두 번째 POST는 캐시 hit — LLM 호출 1회만 발생해야."""
    calls = 0

    async def counting_tutor(**_kwargs):
        nonlocal calls
        calls += 1
        return f"메시지 #{calls}", "gpt-4o-mini"

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", counting_tutor)

    sid = _create_done_submission(client, seeded_problem_id, email="cache@example.com")
    _set_api_key(client)

    r1 = client.post(f"/tutor/{sid}")
    assert r1.status_code == 200
    assert r1.json()["message"] == "메시지 #1"

    r2 = client.post(f"/tutor/{sid}")
    assert r2.status_code == 200
    # 캐시 hit이면 메시지 그대로
    assert r2.json()["message"] == "메시지 #1"
    assert calls == 1


def test_tutor_regenerate_creates_new_message(
    client: TestClient, seeded_problem_id: int, monkeypatch, make_user
):
    """?regenerate=true는 캐시를 무시하고 새 행을 만든다."""
    calls = 0

    async def counting_tutor(**_kwargs):
        nonlocal calls
        calls += 1
        return f"메시지 #{calls}", "gpt-4o-mini"

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", counting_tutor)

    sid = _create_done_submission(client, seeded_problem_id, email="regen@example.com")
    _set_api_key(client)

    client.post(f"/tutor/{sid}")  # 첫 생성
    r2 = client.post(f"/tutor/{sid}?regenerate=true")
    assert r2.status_code == 200
    assert r2.json()["message"] == "메시지 #2"
    assert calls == 2

    # 다시 캐시 모드로 부르면 최신(=#2)이 돌아와야
    r3 = client.post(f"/tutor/{sid}")
    assert r3.json()["message"] == "메시지 #2"
    assert calls == 2


def test_tutor_history_returns_all_revisions(
    client: TestClient, seeded_problem_id: int, monkeypatch, make_user
):
    counter = 0

    async def counting_tutor(**_kwargs):
        nonlocal counter
        counter += 1
        return f"리비전 {counter}", "gpt-4o-mini"

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", counting_tutor)

    sid = _create_done_submission(client, seeded_problem_id, email="hist@example.com")
    _set_api_key(client)

    client.post(f"/tutor/{sid}")
    client.post(f"/tutor/{sid}?regenerate=true")
    client.post(f"/tutor/{sid}?regenerate=true")

    r = client.get(f"/tutor/{sid}/history")
    assert r.status_code == 200
    body = r.json()
    assert body["submission_id"] == sid
    msgs = body["messages"]
    assert [m["message"] for m in msgs] == ["리비전 1", "리비전 2", "리비전 3"]
    # id 단조 증가 + created_at 존재
    ids = [m["id"] for m in msgs]
    assert ids == sorted(ids)
    for m in msgs:
        assert "created_at" in m


def test_tutor_history_404_on_missing_submission(client: TestClient):
    client.cookies.clear()
    client.post("/auth/dev-login", params={"email": "test404@example.com"})
    _set_api_key(client)

    r = client.get("/tutor/999999/history")
    assert r.status_code == 404


def test_tutor_history_empty_for_un_tutored_submission(
    client: TestClient, seeded_problem_id: int, make_user
):
    """채점은 끝났지만 한 번도 튜터링 안 받은 제출 — 200 + 빈 리스트."""
    sid = _create_done_submission(client, seeded_problem_id, email="empty-hist@example.com")
    _set_api_key(client)
    r = client.get(f"/tutor/{sid}/history")
    assert r.status_code == 200
    body = r.json()
    assert body["submission_id"] == sid
    assert body["messages"] == []
    assert body["usage_count"] == 0
    assert body["remaining_uses"] == 3


def test_tutor_404_on_missing_submission(client: TestClient, monkeypatch):
    async def boom(**_kwargs):
        raise AssertionError("OpenAI는 호출되면 안 됨")

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", boom)

    client.cookies.clear()
    client.post("/auth/dev-login", params={"email": "test404@example.com"})
    _set_api_key(client)

    r = client.post("/tutor/999999")
    assert r.status_code == 404


def test_tutor_409_when_submission_not_done(
    client: TestClient, seeded_problem_id: int, monkeypatch, make_user
):
    """status=queued 상태(=채점 안 끝남)에 호출하면 409."""
    from src.storage import get_session
    from src.storage.submissions import create_submission

    # 큐를 거치지 않고 직접 row 삽입 → status 기본값은 "queued"
    user_id = make_user()
    with get_session() as s:
        sid = create_submission(s, user_id=user_id, problem_id=seeded_problem_id, code="x")

    async def boom(**_kwargs):
        raise AssertionError("OpenAI는 호출되면 안 됨")

    import src.api.tutor as tutor_api
    monkeypatch.setattr(tutor_api, "run_tutor", boom)

    client.cookies.clear()
    client.post("/auth/dev-login", params={"email": "test409@example.com"})
    _set_api_key(client)

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
    assert "[Problem]" in msg
    assert "[Author's intent]" in msg
    assert "print('hi')" in msg
    assert "[Test results] 1/3 passed" in msg
    assert "ZeroDivisionError" in msg
    assert "[Judge opinions]" in msg
    assert "Melchior" in msg
    assert "[Final verdict] SUS" in msg


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
    assert "[Judge opinions]" not in msg
    assert "[Final verdict] SUS" in msg
    assert "TLE" in msg
