"""judge._clean_issues — 3-judge가 낸 품질 이슈 정제.

작은 모델이 issues 필드에 넣는 노이즈(중복·공백·'오류:'·길이 이상)를 거르는지.
점수/통과 판정과 무관(별도 필드)하고 대시보드 표시 노이즈만 줄인다.
"""
from __future__ import annotations

from authoring.pipeline.nodes.judge import (
    _ISSUE_MAX_LEN,
    _MAX_ISSUES,
    _clean_issues,
)


def test_dedup_case_insensitive_preserves_order():
    out = _clean_issues([
        "입력 N의 범위가 statement에 없음",
        "입력 N의 범위가 STATEMENT에 없음",  # 대소문자만 다름 → 중복
        "must_handle 'edge'가 테스트 미커버",
    ])
    assert out == ["입력 N의 범위가 statement에 없음", "must_handle 'edge'가 테스트 미커버"]


def test_drops_empty_and_parse_error_and_nonstring():
    out = _clean_issues(["", "   ", "오류: JSONDecodeError ...", None, 123, "유효한 지적 항목"])
    assert out == ["유효한 지적 항목"]


def test_length_bounds():
    short = "음"               # 4자 미만 → 제거
    long = "가" * (_ISSUE_MAX_LEN + 1)  # 상한 초과 → 제거
    ok = "범위 미명시"          # 적당
    assert _clean_issues([short, long, ok]) == [ok]


def test_repeated_hallucination_collapses_to_one():
    # #4 사례: 동일 환각 문구 3회 반복 → 1개로
    g = "안녕시소 집약을 장해세요. 사울의 입해세요 엘코세요."
    assert _clean_issues([g, g, g]) == [g]


def test_caps_at_max():
    many = [f"서로 다른 지적 항목 번호 {i}" for i in range(20)]
    assert len(_clean_issues(many)) == _MAX_ISSUES


def test_empty_in_empty_out():
    assert _clean_issues([]) == []
