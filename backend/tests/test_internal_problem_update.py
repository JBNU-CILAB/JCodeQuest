"""PATCH /internal/problems/{id} — 관리자 문제 수동 수정.

- 스칼라 필드(title/statement/level/points/limits/reference_code) 부분 갱신
- test_cases 전체 교체(delete-orphan)
- intent_rubric 통째 교체
- 인증 가드 / 404
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from src.schemas import IntentRubric, Problem, TestCase
from src.storage import get_session
from src.storage.models import ProblemRow
from src.storage.problems import create_problem


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


def _problem(title: str = "원본") -> Problem:
    return Problem(
        id=0,
        title=title,
        statement="원본 본문",
        category="math",
        level="bronze",
        points=100,
        time_limit_ms=2000,
        memory_limit_mb=256,
        reference_code="print(1)\n",
        intent_rubric=IntentRubric(
            expected_approach="흐름",
            expected_complexity="O(n)",
            must_handle=[],
            forbidden_patterns=[],
            key_insight="통찰",
            one_line_summary="한줄",
        ),
        test_cases=[
            TestCase(ordinal=1, stdin="1\n", expected_stdout="1", is_sample=True),
            TestCase(ordinal=2, stdin="2\n", expected_stdout="2", is_sample=False),
        ],
    )


def _seed() -> int:
    with get_session() as s:
        return create_problem(s, _problem(), status="approved")


def test_patch_scalar_fields_only(client):
    pid = _seed()
    r = client.patch(
        f"/internal/problems/{pid}",
        headers=_auth(),
        json={"title": "수정된 제목", "points": 250, "level": "silver"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "수정된 제목"
    assert body["points"] == 250
    assert body["level"] == "silver"
    # 미지정 필드는 그대로
    assert body["statement"] == "원본 본문"
    assert body["reference_code"] == "print(1)\n"
    assert len(body["test_cases"]) == 2


def test_patch_replaces_test_cases(client):
    pid = _seed()
    r = client.patch(
        f"/internal/problems/{pid}",
        headers=_auth(),
        json={
            "test_cases": [
                {"ordinal": 1, "stdin": "10\n", "expected_stdout": "10", "is_sample": True},
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["test_cases"]) == 1
    assert body["test_cases"][0]["stdin"] == "10\n"
    # DB도 실제로 1개만 남아야 한다 (delete-orphan)
    with get_session() as s:
        row = s.get(ProblemRow, pid)
        assert len(row.test_cases) == 1


def test_patch_404_when_missing(client):
    r = client.patch(
        "/internal/problems/99999",
        headers=_auth(),
        json={"title": "X"},
    )
    assert r.status_code == 404


def test_patch_requires_auth(client):
    pid = _seed()
    r = client.patch(f"/internal/problems/{pid}", json={"title": "x"})
    assert r.status_code == 401
