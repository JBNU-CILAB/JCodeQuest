"""GET /internal/users, DELETE /internal/users/{id}, DELETE /internal/users/{id}/api-key.

- 인증 (Bearer JCQ_INTERNAL_SECRET) 가드
- 목록 출력 — has_api_key/submission_count
- search 부분 일치
- cascade 삭제 — submission/tutor_message/session/api_key 모두 정리
- 404 / idempotent 키 제거
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from src.storage import get_session
from src.storage.models import (
    SessionRow,
    SubmissionRow,
    TutorMessageRow,
    UserRow,
)
from src.storage.problems import create_problem
from src.storage.sessions import create_session
from src.storage.submissions import create_submission
from src.storage.tutor import create_tutor_message
from src.storage.users import set_user_api_key


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


def test_list_users_requires_auth(client):
    assert client.get("/internal/users").status_code == 401


def test_list_users_returns_submission_count_and_api_key_flag(
    client, sample_problem, make_user
):
    """submission_count는 cascade 영향 미리보기로 노출돼야 한다."""
    uid = make_user(display_name="목록테스트")
    with get_session() as s:
        pid = create_problem(s, sample_problem, status="approved")
        create_submission(s, user_id=uid, problem_id=pid, code="x = 1\n")
        create_submission(s, user_id=uid, problem_id=pid, code="x = 2\n")
        set_user_api_key(s, uid, api_key="dummy-key")

    r = client.get("/internal/users", params={"search": "목록테스트"}, headers=_auth())
    assert r.status_code == 200, r.text
    rows = r.json()
    me = next(row for row in rows if row["id"] == uid)
    assert me["display_name"] == "목록테스트"
    assert me["has_api_key"] is True
    assert me["submission_count"] == 2


def test_list_users_search_partial(client, make_user):
    a = make_user(display_name="알파베타")
    b = make_user(display_name="감마델타")

    r = client.get("/internal/users", params={"search": "알파"}, headers=_auth())
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert a in ids and b not in ids


def test_delete_user_cascades_all(client, sample_problem, make_user):
    """제출 / 튜터 메시지 / 세션 / API 키 모두 함께 사라져야 한다."""
    uid = make_user(display_name="삭제대상")
    with get_session() as s:
        pid = create_problem(s, sample_problem, status="approved")
        sid1 = create_submission(s, user_id=uid, problem_id=pid, code="x = 1\n")
        sid2 = create_submission(s, user_id=uid, problem_id=pid, code="x = 2\n")
        create_tutor_message(s, submission_id=sid1, message="tm1")
        create_tutor_message(s, submission_id=sid1, message="tm2")
        create_tutor_message(s, submission_id=sid2, message="tm3")
        create_session(s, user_id=uid, ttl_days=7)
        create_session(s, user_id=uid, ttl_days=7)
        set_user_api_key(s, uid, api_key="dummy-key")

    r = client.delete(f"/internal/users/{uid}", headers=_auth())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == uid
    assert body["cascade"] == {
        "submissions": 2,
        "tutor_messages": 3,
        "sessions": 2,
    }

    # 실제로 모두 사라졌는지 DB 직접 확인.
    with get_session() as s:
        assert s.get(UserRow, uid) is None
        assert list(s.exec(
            select(SubmissionRow).where(SubmissionRow.user_id == uid)
        )) == []
        assert list(s.exec(
            select(TutorMessageRow).where(
                TutorMessageRow.submission_id.in_([sid1, sid2])  # type: ignore[attr-defined]
            )
        )) == []
        assert list(s.exec(
            select(SessionRow).where(SessionRow.user_id == uid)
        )) == []


def test_delete_user_not_found(client):
    r = client.delete("/internal/users/9999999", headers=_auth())
    assert r.status_code == 404


def test_clear_api_key(client, make_user):
    uid = make_user()
    with get_session() as s:
        set_user_api_key(s, uid, api_key="dummy-key")
        row = s.get(UserRow, uid)
        assert row is not None and row.api_key_secret_id is not None

    r = client.delete(f"/internal/users/{uid}/api-key", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json() == {"id": uid, "cleared": True}

    with get_session() as s:
        row = s.get(UserRow, uid)
        assert row is not None and row.api_key_secret_id is None


def test_clear_api_key_idempotent_when_unset(client, make_user):
    """이미 키가 없던 유저에게도 200 응답 — UI에서 강제로 다시 누른 경우 대비."""
    uid = make_user()
    r = client.delete(f"/internal/users/{uid}/api-key", headers=_auth())
    assert r.status_code == 200


def test_clear_api_key_404(client):
    r = client.delete("/internal/users/9999999/api-key", headers=_auth())
    assert r.status_code == 404
