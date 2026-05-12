"""Auth 라우터 + 서버 측 세션 + /me 검증.

Google OAuth 콜백은 authlib의 authorize_access_token을 monkeypatch로 갈아끼워서
외부 IdP 의존 없이 검증한다."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.auth.deps import SESSION_COOKIE
from src.storage import get_session
from src.storage.models import SessionRow
from src.storage.sessions import (
    create_session,
    delete_session,
    get_session_user,
    purge_expired,
)


# ───────────────────────── unit: SessionRow 헬퍼 ─────────────────────────


def test_session_create_and_lookup_returns_user(make_user):
    user_id = make_user()
    with get_session() as s:
        token, expires_at = create_session(s, user_id=user_id, ttl_days=7)
        u = get_session_user(s, token)
        assert u is not None
        assert u.id == user_id
    assert expires_at > datetime.now(timezone.utc)


def test_session_lookup_unknown_token_returns_none():
    with get_session() as s:
        assert get_session_user(s, "no-such-token") is None


def test_session_expired_returns_none_and_is_purged_lazily(make_user):
    user_id = make_user()
    with get_session() as s:
        token, _ = create_session(s, user_id=user_id, ttl_days=7)
        # 만료를 과거로 강제
        row = s.get(SessionRow, token)
        assert row is not None
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.add(row)
        s.commit()

    with get_session() as s:
        assert get_session_user(s, token) is None
        # lazy purge — lookup 한 번에 row가 사라져야
        assert s.get(SessionRow, token) is None


def test_session_delete_idempotent(make_user):
    user_id = make_user()
    with get_session() as s:
        token, _ = create_session(s, user_id=user_id, ttl_days=7)

    with get_session() as s:
        assert delete_session(s, token) is True
        assert delete_session(s, token) is False  # 이미 없음
        assert get_session_user(s, token) is None


def test_purge_expired_removes_only_expired(make_user):
    u1, u2 = make_user(), make_user()
    with get_session() as s:
        live, _ = create_session(s, user_id=u1, ttl_days=7)
        dead, _ = create_session(s, user_id=u2, ttl_days=7)
        # dead만 과거로
        row = s.get(SessionRow, dead)
        assert row is not None
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        s.add(row)
        s.commit()

    with get_session() as s:
        n = purge_expired(s)
        assert n == 1
        assert s.get(SessionRow, dead) is None
        assert s.get(SessionRow, live) is not None


# ───────────────────────── dev stub flow (HTTP) ─────────────────────────


@pytest.fixture
def client():
    from src.main import app
    with TestClient(app) as c:
        yield c


def test_dev_login_sets_cookie_and_me_works(client: TestClient):
    r = client.post(
        "/auth/dev-login",
        params={"email": "dev@example.com", "name": "개발자"},
    )
    assert r.status_code == 200, r.text
    assert SESSION_COOKIE in client.cookies

    r2 = client.get("/me")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["email"] == "dev@example.com"
    assert body["display_name"] == "개발자"
    assert body["provider"] == "dev_stub"
    assert body["exp"] == 0
    assert body["tier"] == "bronze"


def test_me_without_cookie_returns_401(client: TestClient):
    r = client.get("/me")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_me_with_invalid_cookie_returns_401(client: TestClient):
    client.cookies.set(SESSION_COOKIE, "totally-not-a-valid-session-token")
    r = client.get("/me")
    assert r.status_code == 401


def test_logout_invalidates_session_server_side(client: TestClient):
    """JWT와 달리 logout이 진짜 끊음 — 같은 토큰을 들고 와도 거부되어야."""
    client.post("/auth/dev-login", params={"email": "x@example.com"})
    token = client.cookies.get(SESSION_COOKIE)
    assert token is not None

    r = client.post("/auth/logout")
    assert r.status_code == 200
    assert SESSION_COOKIE not in client.cookies

    # 같은 토큰을 직접 다시 박아도 401 — 서버 측 row가 삭제됐기 때문
    client.cookies.set(SESSION_COOKIE, token)
    r2 = client.get("/me")
    assert r2.status_code == 401


def test_dev_login_idempotent_user_but_new_session(client: TestClient):
    """같은 email로 두 번 로그인하면 user는 같지만 SessionRow는 별개여야 (다중 디바이스 가정)."""
    r1 = client.post("/auth/dev-login", params={"email": "same@example.com"})
    uid1 = r1.json()["user_id"]
    token1 = client.cookies.get(SESSION_COOKIE)

    from src.main import app
    with TestClient(app) as c2:
        r2 = c2.post("/auth/dev-login", params={"email": "same@example.com"})
        uid2 = r2.json()["user_id"]
        token2 = c2.cookies.get(SESSION_COOKIE)

    assert uid1 == uid2
    assert token1 != token2  # 별도 세션


# ───────────────────────── Google callback (mocked) ─────────────────────────


def _patch_google_token(monkeypatch, userinfo: dict):
    """authlib OAuth의 authorize_access_token만 갈아끼움."""
    from src.auth.google import get_oauth

    async def fake_authorize(request):
        return {"userinfo": userinfo}

    oauth = get_oauth()
    monkeypatch.setattr(oauth.google, "authorize_access_token", fake_authorize)


def test_callback_happy_path_sets_session(client: TestClient, monkeypatch):
    _patch_google_token(monkeypatch, {
        "sub": "google-sub-123",
        "email": "student@jbnu.ac.kr",
        "email_verified": True,
        "name": "홍길동",
        "hd": "jbnu.ac.kr",
    })

    r = client.get("/auth/callback", follow_redirects=False)
    assert r.status_code == 302
    assert SESSION_COOKIE in client.cookies

    me = client.get("/me").json()
    assert me["email"] == "student@jbnu.ac.kr"
    assert me["display_name"] == "홍길동"
    assert me["provider"] == "google"


def test_callback_rejects_wrong_hd(client: TestClient, monkeypatch):
    _patch_google_token(monkeypatch, {
        "sub": "google-sub-out",
        "email": "outsider@gmail.com",
        "email_verified": True,
        "name": "외부인",
        "hd": "gmail.com",
    })

    r = client.get("/auth/callback", follow_redirects=False)
    assert r.status_code == 403
    assert SESSION_COOKIE not in client.cookies


def test_callback_rejects_missing_hd(client: TestClient, monkeypatch):
    """개인 gmail 계정은 hd claim 자체가 없음 — 거부되어야."""
    _patch_google_token(monkeypatch, {
        "sub": "google-sub-private",
        "email": "private@gmail.com",
        "email_verified": True,
        "name": "사적 유저",
        # "hd": 없음
    })

    r = client.get("/auth/callback", follow_redirects=False)
    assert r.status_code == 403


def test_callback_rejects_unverified_email(client: TestClient, monkeypatch):
    _patch_google_token(monkeypatch, {
        "sub": "google-sub-unverified",
        "email": "unverified@jbnu.ac.kr",
        "email_verified": False,
        "name": "미인증",
        "hd": "jbnu.ac.kr",
    })

    r = client.get("/auth/callback", follow_redirects=False)
    assert r.status_code == 403


def test_callback_second_login_returns_same_user(client: TestClient, monkeypatch):
    userinfo = {
        "sub": "stable-google-sub",
        "email": "repeat@jbnu.ac.kr",
        "email_verified": True,
        "name": "재로그인",
        "hd": "jbnu.ac.kr",
    }
    _patch_google_token(monkeypatch, userinfo)

    client.get("/auth/callback", follow_redirects=False)
    uid1 = client.get("/me").json()["id"]

    client.cookies.clear()
    client.get("/auth/callback", follow_redirects=False)
    uid2 = client.get("/me").json()["id"]

    assert uid1 == uid2
