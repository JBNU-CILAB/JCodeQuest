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
        "id", "title", "category", "level", "points", "one_line_summary", "iso_week"
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


def _force_week(problem_id: int, week: str) -> None:
    """create 후 iso_week 컬럼을 강제로 갈아끼워 주차별 픽스처를 만든다.
    default_factory가 '지금 주차'를 박는 게 정상 동작이므로 테스트만 우회."""
    from src.storage.models import ProblemRow
    with get_session() as s:
        row = s.get(ProblemRow, problem_id)
        assert row is not None
        row.iso_week = week
        s.add(row)
        s.commit()


def test_summary_carries_iso_week_for_current_week(client: TestClient):
    from src.storage.models import iso_week_of
    from datetime import datetime, timezone

    with get_session() as s:
        pid = create_problem(s, _make_problem(title="주차표시"), status="approved")

    expected = iso_week_of(datetime.now(timezone.utc))
    r = client.get("/problems")
    assert r.status_code == 200
    item = next(p for p in r.json() if p["id"] == pid)
    assert item["iso_week"] == expected


def test_weeks_endpoint_groups_approved_and_excludes_draft(client: TestClient):
    with get_session() as s:
        a = create_problem(s, _make_problem(title="A"), status="approved")
        b = create_problem(s, _make_problem(title="B"), status="approved")
        c = create_problem(s, _make_problem(title="C"), status="approved")
        d = create_problem(s, _make_problem(title="D-draft"), status="draft")

    _force_week(a, "2026-W18")
    _force_week(b, "2026-W18")
    _force_week(c, "2026-W19")
    _force_week(d, "2026-W19")  # draft — 집계에서 제외돼야 함

    r = client.get("/problems/weeks")
    assert r.status_code == 200
    buckets = r.json()["buckets"]
    weeks = {b["week"]: b["count"] for b in buckets}
    assert weeks.get("2026-W18") == 2
    assert weeks.get("2026-W19") == 1
    # 내림차순 (최신 주가 먼저)
    listed = [b["week"] for b in buckets if b["week"].startswith("2026-W1")]
    assert listed == sorted(listed, reverse=True)


def test_weekly_bucket_listing_returns_summaries(client: TestClient):
    with get_session() as s:
        a = create_problem(s, _make_problem(title="P-A"), status="approved")
        b = create_problem(s, _make_problem(title="P-B"), status="approved")
        other = create_problem(s, _make_problem(title="P-other"), status="approved")
        draft = create_problem(s, _make_problem(title="P-draft"), status="draft")

    _force_week(a, "2020-W05")
    _force_week(b, "2020-W05")
    _force_week(other, "2020-W06")
    _force_week(draft, "2020-W05")

    r = client.get("/problems/weeks/2020-W05")
    assert r.status_code == 200
    items = r.json()
    ids = {p["id"] for p in items}
    assert ids == {a, b}
    assert all(p["iso_week"] == "2020-W05" for p in items)
    # 비밀 필드 누설 없음
    assert "SECRET" not in r.text
    assert "reference_code" not in r.text


def test_weekly_bucket_unknown_week_returns_empty_list(client: TestClient):
    r = client.get("/problems/weeks/1999-W01")
    assert r.status_code == 200
    assert r.json() == []
