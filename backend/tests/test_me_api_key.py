"""PUT /me/api-key — Vault 저장 + has_api_key 반영. SQLite엔 vault가 없으므로
storage.vault의 fallback이 식별자=값으로 들어가는 경로를 함께 검증한다."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.storage import get_session
from src.storage.models import UserRow
from src.storage.users import get_user_api_key


@pytest.fixture
def client():
    from src.main import app

    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str = "key@example.com") -> int:
    r = client.post("/auth/dev-login", params={"email": email, "name": "키유저"})
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


def test_put_api_key_persists_and_me_reports_has_api_key(client: TestClient):
    user_id = _login(client)

    r0 = client.get("/me")
    assert r0.status_code == 200
    assert r0.json()["has_api_key"] is False

    key = "sk-test-" + "a" * 24  # 32자 인쇄 가능 ASCII
    r = client.put("/me/api-key", json={"api_key": key})
    assert r.status_code == 200, r.text
    assert r.json() == {"has_api_key": True}

    r2 = client.get("/me")
    assert r2.status_code == 200
    assert r2.json()["has_api_key"] is True

    # vault.read_secret 라운드트립 (sqlite fallback에선 id=값이라 그대로 복호화됨)
    with get_session() as s:
        assert get_user_api_key(s, user_id) == key
        row = s.get(UserRow, user_id)
        assert row is not None
        assert row.api_key_secret_id is not None


def test_put_api_key_overwrites_existing(client: TestClient):
    user_id = _login(client, email="key2@example.com")
    first = "sk-first-" + "b" * 24
    second = "sk-second-" + "c" * 24
    client.put("/me/api-key", json={"api_key": first})
    client.put("/me/api-key", json={"api_key": second})
    with get_session() as s:
        assert get_user_api_key(s, user_id) == second


def test_put_api_key_requires_auth(client: TestClient):
    # 길이는 정규식 통과해도 auth 미보유면 401 — 검증보다 인증이 먼저 평가됨을 확인.
    r = client.put("/me/api-key", json={"api_key": "x" * 32})
    assert r.status_code == 401


def test_put_api_key_rejects_empty(client: TestClient):
    _login(client, email="key3@example.com")
    r = client.put("/me/api-key", json={"api_key": ""})
    assert r.status_code == 422


def test_put_api_key_rejects_whitespace_and_short(client: TestClient):
    """공백/개행 섞임이나 너무 짧은 값은 422 — 마스킹 핸들러가 input을 [REDACTED]로 치환."""
    _login(client, email="key4@example.com")

    # 너무 짧음
    r1 = client.put("/me/api-key", json={"api_key": "short"})
    assert r1.status_code == 422
    body1 = r1.json()
    assert body1["detail"][0]["input"] == "[REDACTED]"

    # 공백 포함 (정규식 위반)
    r2 = client.put("/me/api-key", json={"api_key": "sk-leading space" + "x" * 20})
    assert r2.status_code == 422
    assert r2.json()["detail"][0]["input"] == "[REDACTED]"

    # 개행 포함
    r3 = client.put("/me/api-key", json={"api_key": "sk-newline\n" + "x" * 24})
    assert r3.status_code == 422
    assert r3.json()["detail"][0]["input"] == "[REDACTED]"
