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

    r = client.put("/me/api-key", json={"api_key": "sk-test-abc123"})
    assert r.status_code == 200, r.text
    assert r.json() == {"has_api_key": True}

    r2 = client.get("/me")
    assert r2.status_code == 200
    assert r2.json()["has_api_key"] is True

    # vault.read_secret 라운드트립 (sqlite fallback에선 id=값이라 그대로 복호화됨)
    with get_session() as s:
        assert get_user_api_key(s, user_id) == "sk-test-abc123"
        row = s.get(UserRow, user_id)
        assert row is not None
        assert row.api_key_secret_id is not None


def test_put_api_key_overwrites_existing(client: TestClient):
    user_id = _login(client, email="key2@example.com")
    client.put("/me/api-key", json={"api_key": "first"})
    client.put("/me/api-key", json={"api_key": "second"})
    with get_session() as s:
        assert get_user_api_key(s, user_id) == "second"


def test_put_api_key_requires_auth(client: TestClient):
    r = client.put("/me/api-key", json={"api_key": "x"})
    assert r.status_code == 401


def test_put_api_key_rejects_empty(client: TestClient):
    _login(client, email="key3@example.com")
    r = client.put("/me/api-key", json={"api_key": ""})
    assert r.status_code == 422
