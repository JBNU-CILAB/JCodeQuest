"""실 Ollama에 붙어 sandbox + 3-judge ensemble을 통째로 돌리는 시나리오 슈트.

실행:
    source backend/env.sh
    JCQ_RUN_LIVE_LLM=1 .venv/bin/pytest tests/live -v -s

각 시나리오는 `recorder.write()`로 즉시 JSONL에 flush하므로,
- 중간에 죽어도 직전까지의 결과가 디스크에 남고
- 세션 끝에 markdown 요약이 자동 생성됨.

LLM 응답은 비결정적이라 expected_verdict와 actual이 어긋날 수 있다.
그 경우 테스트는 fail로 표시되지만 markdown에 UNEXPECTED 라벨로 따로 보이게 해놨다 —
사고가 아니라 분석 대상.
"""
from __future__ import annotations

import time

import pytest

from src.judge.ensemble import vote
from src.judge.sandbox import run_all_tests
from src.schemas import Problem

from .conftest import GradeOutcome, LiveRunRecorder


async def _grade_full(
    problem: Problem, code: str, ollama_url: str
) -> GradeOutcome:
    """grade_submission의 핵심 로직을 DB 없이 그대로 재현."""
    t0 = time.monotonic()
    test_results = run_all_tests(
        code,
        problem.test_cases,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
    )
    all_passed = bool(test_results) and all(r.passed for r in test_results)

    ensemble = None
    verdict = "SUS"
    if all_passed:
        ensemble = await vote(problem, code, test_results, base_url=ollama_url)
        verdict = ensemble.final_verdict

    return GradeOutcome(
        verdict=verdict,
        test_results=test_results,
        ensemble=ensemble,
        elapsed_s=time.monotonic() - t0,
    )


def _record(
    recorder: LiveRunRecorder,
    *,
    name: str,
    expected: str | None,
    code: str,
    outcome: GradeOutcome,
    notes: str = "",
    passed_assertion: bool | None = None,
) -> None:
    from .conftest import ScenarioRecord

    rec = ScenarioRecord(
        name=name,
        expected_verdict=expected,
        code=code,
        test_results=[t.model_dump() for t in outcome.test_results],
        ensemble=outcome.ensemble.model_dump() if outcome.ensemble else None,
        actual_verdict=outcome.verdict,
        elapsed_s=outcome.elapsed_s,
        notes=notes,
        passed_assertion=passed_assertion,
    )
    recorder.write(rec)


# ──────────────────────────── AC 시나리오 ────────────────────────────


async def test_ac_clean_factorial(
    recorder: LiveRunRecorder, ollama_url: str, factorial_problem: Problem
) -> None:
    """정석적인 누적 곱 → 모든 판사 AC 기대."""
    code = (
        "n = int(input())\n"
        "r = 1\n"
        "for i in range(1, n + 1):\n"
        "    r *= i\n"
        "print(r)\n"
    )
    out = await _grade_full(factorial_problem, code, ollama_url)
    expected = "AC"
    matched = out.verdict == expected
    _record(
        recorder,
        name="ac_clean_factorial",
        expected=expected,
        code=code,
        outcome=out,
        notes="정석 루프 구현 — 의도 명세와 정확히 일치",
        passed_assertion=matched,
    )
    assert out.test_results and all(t.passed for t in out.test_results)
    assert out.ensemble is not None and len(out.ensemble.votes) == 3
    assert out.verdict == expected


async def test_ac_recursive_factorial(
    recorder: LiveRunRecorder, ollama_url: str, factorial_problem: Problem
) -> None:
    """재귀로도 정답 — 의도 명세에 '또는 재귀'가 명시돼 있어 AC 기대."""
    code = (
        "import sys\n"
        "sys.setrecursionlimit(100)\n"
        "def f(n):\n"
        "    return 1 if n <= 1 else n * f(n - 1)\n"
        "print(f(int(input())))\n"
    )
    out = await _grade_full(factorial_problem, code, ollama_url)
    expected = "AC"
    matched = out.verdict == expected
    _record(
        recorder,
        name="ac_recursive_factorial",
        expected=expected,
        code=code,
        outcome=out,
        notes="재귀 풀이 — rubric의 '또는 재귀'에 부합",
        passed_assertion=matched,
    )
    assert out.test_results and all(t.passed for t in out.test_results)
    assert out.ensemble is not None
    # 재귀 vs 루프는 둘 다 적법 — verdict는 AC여야 함.
    assert out.verdict == expected


# ──────────────────────────── SUS 시나리오 ────────────────────────────


async def test_sus_hardcoded_factorial(
    recorder: LiveRunRecorder, ollama_url: str, factorial_problem: Problem
) -> None:
    """모든 테스트 입력에 대해 if/elif 매핑으로 정답을 찍음 → 테스트는 통과하지만 의도 위배.

    rubric의 forbidden_patterns에 '하드코딩된 if/elif 분기'가 명시돼 있으므로
    이상적으로는 ensemble이 SUS로 합의해야 함. LLM이 못 잡으면 그것 자체가 흥미로운 시그널.
    """
    code = (
        "n = int(input())\n"
        "if n == 0:\n"
        "    print(1)\n"
        "elif n == 1:\n"
        "    print(1)\n"
        "elif n == 5:\n"
        "    print(120)\n"
        "elif n == 12:\n"
        "    print(479001600)\n"
        "else:\n"
        "    print(0)\n"
    )
    out = await _grade_full(factorial_problem, code, ollama_url)
    expected = "SUS"
    matched = out.verdict == expected
    _record(
        recorder,
        name="sus_hardcoded_factorial",
        expected=expected,
        code=code,
        outcome=out,
        notes="테스트는 통과하지만 if/elif 매핑 — 의도 위배. 판사가 못 잡으면 ensemble 약점.",
        passed_assertion=matched,
    )
    assert out.test_results and all(t.passed for t in out.test_results)
    assert out.ensemble is not None
    # 이건 LLM 품질에 좌우됨 — 못 잡으면 fail로 표면화시키는 게 의도.
    assert out.verdict == expected


# ────────────────────── 샌드박스 단계에서 이미 SUS ──────────────────────


async def test_wa_skips_llm(
    recorder: LiveRunRecorder, ollama_url: str, factorial_problem: Problem
) -> None:
    """오답 → 테스트 단계에서 SUS 확정, LLM 미호출 (ensemble=None 기록)."""
    code = "n = int(input())\nprint(n + 1)  # 잘못된 식\n"
    out = await _grade_full(factorial_problem, code, ollama_url)
    expected = "SUS"
    matched = out.verdict == expected and out.ensemble is None
    _record(
        recorder,
        name="wa_skips_llm",
        expected=expected,
        code=code,
        outcome=out,
        notes="WA → 테스트 단계에서 SUS, LLM 미호출 (no-LLM 경로 검증)",
        passed_assertion=matched,
    )
    assert out.ensemble is None  # ★ LLM 미호출
    assert out.verdict == "SUS"


async def test_re_skips_llm(
    recorder: LiveRunRecorder, ollama_url: str, factorial_problem: Problem
) -> None:
    """런타임 에러 → 테스트 RE → SUS, LLM 미호출."""
    code = "n = int(input())\nprint(1 / 0)\n"
    out = await _grade_full(factorial_problem, code, ollama_url)
    matched = out.verdict == "SUS" and out.ensemble is None
    _record(
        recorder,
        name="re_skips_llm",
        expected="SUS",
        code=code,
        outcome=out,
        notes="ZeroDivisionError → RE → LLM 미호출",
        passed_assertion=matched,
    )
    assert out.ensemble is None
    assert any(t.status == "RE" for t in out.test_results)


async def test_tle_skips_llm(
    recorder: LiveRunRecorder, ollama_url: str, factorial_problem: Problem
) -> None:
    """무한 루프 → TLE → SUS, LLM 미호출."""
    code = "n = int(input())\nwhile True:\n    pass\n"
    out = await _grade_full(factorial_problem, code, ollama_url)
    matched = out.verdict == "SUS" and out.ensemble is None
    _record(
        recorder,
        name="tle_skips_llm",
        expected="SUS",
        code=code,
        outcome=out,
        notes="무한 루프 → TLE → LLM 미호출",
        passed_assertion=matched,
    )
    assert out.ensemble is None
    assert any(t.status == "TLE" for t in out.test_results)


# ────────────────────────── trivial 문제 보너스 ──────────────────────────


async def test_ac_double_simple(
    recorder: LiveRunRecorder, ollama_url: str, double_problem: Problem
) -> None:
    """conftest의 기본 문제와 동등 — ensemble 기본 AC 흐름 sanity check."""
    code = "n = int(input())\nprint(n * 2)\n"
    out = await _grade_full(double_problem, code, ollama_url)
    matched = out.verdict == "AC"
    _record(
        recorder,
        name="ac_double_simple",
        expected="AC",
        code=code,
        outcome=out,
        notes="trivial 케이스 — ensemble이 기본 AC를 안정적으로 내는지 확인",
        passed_assertion=matched,
    )
    assert out.verdict == "AC"
    assert out.ensemble is not None
