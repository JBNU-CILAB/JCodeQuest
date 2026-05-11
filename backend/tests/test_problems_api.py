"""GET /problems, GET /problems/{id} 라우터 검사.
- 응답에 reference_code / intent_rubric 전체 / hidden test case 누설 없음
- status != 'approved' 인 문제는 노출되지 않음
- category / level 필터 동작
"""
import pytest
from fastapi.testclient import TestClient

from src.schemas import IntentRubric, Problem, TestCase
from src.storage import get_session
from src.storage.problems import create_problem


@pytest.fixture
def client():
    from src.main import app
    with TestClient(app) as c:
        yield c


def _make_problem(
    *, title: str, category: str = "basic", level: str = "bronze"
) -> Problem:
    return Problem(
        id=0,
        title=title,
        statement=f"{title} 문제 본문",
        category=category,
        level=level,  # type: ignore[arg-type]
        points=100,
        time_limit_ms=1000,
        memory_limit_mb=128,
        reference_code="SECRET_REFERENCE_CODE_SHOULD_NEVER_LEAK\n",
        intent_rubric=IntentRubric(
            expected_approach="SECRET approach",
            expected_complexity="O(1)",
            must_handle=["SECRET must"],
            forbidden_patterns=["SECRET forbidden"],
            key_insight="SECRET insight",
            one_line_summary=f"{title} 한 줄 요약",
        ),
        test_cases=[
            TestCase(ordinal=1, stdin="1\n", expected_stdout="sample-out", is_sample=True),
            TestCase(ordinal=2, stdin="SECRET-HIDDEN-IN", expected_stdout="SECRET-HIDDEN-OUT"),
        ],
    )


def test_list_returns_only_approved(client: TestClient):
    with get_session() as s:
        approved_id = create_problem(s, _make_problem(title="공개문제"), status="approved")
        draft_id = create_problem(s, _make_problem(title="초안문제"), status="draft")

    r = client.get("/problems")
    assert r.status_code == 200
    body = r.json()
    ids = {p["id"] for p in body}
    assert approved_id in ids
    assert draft_id not in ids


def test_list_filters_by_category_and_level(client: TestClient):
    with get_session() as s:
        a = create_problem(
            s,
            _make_problem(title="DP-Silver", category="dp", level="silver"),
            status="approved",
        )
        b = create_problem(
            s,
            _make_problem(title="DP-Bronze", category="dp", level="bronze"),
            status="approved",
        )
        c = create_problem(
            s,
            _make_problem(title="Greedy-Silver", category="greedy", level="silver"),
            status="approved",
        )

    r = client.get("/problems", params={"category": "dp"})
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert {a, b}.issubset(ids)
    assert c not in ids

    r = client.get("/problems", params={"category": "dp", "level": "silver"})
    ids = {p["id"] for p in r.json()}
    assert a in ids
    assert b not in ids
    assert c not in ids


def test_list_summary_shape_hides_secrets(client: TestClient):
    with get_session() as s:
        pid = create_problem(s, _make_problem(title="요약확인"), status="approved")

    r = client.get("/problems")
    assert r.status_code == 200
    item = next(p for p in r.json() if p["id"] == pid)
    assert set(item.keys()) == {
        "id", "title", "category", "level", "points", "one_line_summary"
    }
    assert "SECRET" not in r.text


def test_detail_returns_only_sample_cases_and_no_secrets(client: TestClient):
    with get_session() as s:
        pid = create_problem(s, _make_problem(title="상세확인"), status="approved")

    r = client.get(f"/problems/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == pid
    assert body["title"] == "상세확인"
    assert body["one_line_summary"] == "상세확인 한 줄 요약"

    samples = body["sample_test_cases"]
    assert len(samples) == 1
    assert samples[0]["stdin"] == "1\n"
    assert samples[0]["expected_stdout"] == "sample-out"

    # 비밀 필드/숨김 케이스가 직렬화되지 않았는지 raw 응답에서 확인
    assert "SECRET" not in r.text
    assert "reference_code" not in body
    assert "intent_rubric" not in body


def test_detail_404_for_unknown_id(client: TestClient):
    r = client.get("/problems/9999999")
    assert r.status_code == 404


def test_detail_404_for_draft_problem(client: TestClient):
    with get_session() as s:
        draft_id = create_problem(s, _make_problem(title="비공개초안"), status="draft")

    r = client.get(f"/problems/{draft_id}")
    assert r.status_code == 404
