"""실 OpenAI(또는 OpenAI 호환 엔드포인트)에 붙여 튜터 출력을 검수하는 시나리오 슈트.

채점 ensemble과 분리: 사전에 만든 test_results + votes를 입력으로 넣어
튜터 모델의 응답 톤·정답 노출 여부를 사람이 markdown 아티팩트로 검수한다.

실행:
    source backend/env.sh
    export OPENAI_API_KEY=sk-...
    # (선택) export OPENAI_BASE_URL=http://localhost:8000/v1
    # (선택) export OPENAI_MODEL=gpt-4o-mini
    JCQ_RUN_LIVE_LLM=1 .venv/bin/pytest tests/live/test_live_tutor.py -v -s
"""
from __future__ import annotations

import time

from src.schemas import JudgeVote, Problem, TestResult
from src.tutor import tutor as run_tutor

from .conftest import LiveTutorRecorder, TutorScenarioRecord


# ─────────────────────── 보조 ───────────────────────


def _ok(ord_: int, ms: int = 12, kb: int = 8000) -> dict:
    return TestResult(
        ordinal=ord_, passed=True, status="OK",
        elapsed_ms=ms, peak_memory_kb=kb,
    ).model_dump()


def _wa(ord_: int, actual: str) -> dict:
    return TestResult(
        ordinal=ord_, passed=False, status="OK",
        actual_stdout=actual, elapsed_ms=11, peak_memory_kb=8000,
    ).model_dump()


def _re(ord_: int, err: str) -> dict:
    return TestResult(
        ordinal=ord_, passed=False, status="RE",
        error=err, elapsed_ms=20, peak_memory_kb=0,
    ).model_dump()


def _vote(jid: str, verdict: str, intent_match: bool, conf: float, why: str) -> dict:
    return JudgeVote(
        judge_id=jid, verdict=verdict, intent_match=intent_match,
        confidence=conf, rationale=why,
    ).model_dump()


async def _run(
    *,
    name: str,
    problem: Problem,
    code: str,
    verdict: str,
    votes: list[dict] | None,
    test_results: list[dict],
    notes: str,
) -> TutorScenarioRecord:
    t0 = time.monotonic()
    msg, model = await run_tutor(
        problem=problem,
        code=code,
        verdict=verdict,
        votes=votes,
        test_results=test_results,
    )
    return TutorScenarioRecord(
        name=name,
        problem_title=problem.title,
        verdict=verdict,
        code=code,
        votes=votes,
        test_results=test_results,
        model=model,
        message=msg,
        elapsed_s=time.monotonic() - t0,
        notes=notes,
    )


# ─────────────────────── 시나리오 ───────────────────────


async def test_tutor_ac_clean_factorial(
    tutor_recorder: LiveTutorRecorder, factorial_problem: Problem
):
    """AC + 만장일치 — 격려 + 효율/스타일 한 가지 제안 톤 기대."""
    code = (
        "n = int(input())\n"
        "r = 1\n"
        "for i in range(1, n + 1):\n"
        "    r *= i\n"
        "print(r)\n"
    )
    rec = await _run(
        name="tutor_ac_clean_factorial",
        problem=factorial_problem,
        code=code,
        verdict="AC",
        votes=[
            _vote("Melchior", "AC", True, 1.0, "정공법 누적 곱"),
            _vote("Balthasar", "AC", True, 0.95, "O(n) 적합"),
            _vote("Casper", "AC", True, 1.0, "0! 처리 OK"),
        ],
        test_results=[_ok(i) for i in range(1, 5)],
        notes="AC unanimous — 격려 + 사소한 스타일 개선 한 가지 기대",
    )
    tutor_recorder.write(rec)
    assert rec.message


async def test_tutor_majority_ac_split(
    tutor_recorder: LiveTutorRecorder, factorial_problem: Problem
):
    """majority(2:1) AC — 실제 ensemble 라이브 결과와 같은 분포.
    한 판사(Balthasar)가 SUS 의견을 냈는데 튜터가 어떻게 종합하는지 검수."""
    code = (
        "import sys\n"
        "sys.setrecursionlimit(100)\n"
        "def f(n):\n"
        "    return 1 if n <= 1 else n * f(n - 1)\n"
        "print(f(int(input())))\n"
    )
    rec = await _run(
        name="tutor_majority_ac_split",
        problem=factorial_problem,
        code=code,
        verdict="AC",
        votes=[
            _vote("Melchior", "AC", True, 1.0, "재귀 풀이로 모든 입력 처리"),
            _vote("Balthasar", "SUS", False, 0.8,
                  "1부터 n까지 누적 곱에 부합하지 않음"),
            _vote("Casper", "AC", True, 1.0,
                  "0! = 1, n! = n × (n-1)! 핵심 통찰 반영"),
        ],
        test_results=[_ok(i) for i in range(1, 5)],
        notes="majority AC — 한 판사가 SUS 반대표. 튜터가 minority를 어떻게 다루는지",
    )
    tutor_recorder.write(rec)
    assert rec.message


async def test_tutor_sus_hardcoded_factorial(
    tutor_recorder: LiveTutorRecorder, factorial_problem: Problem
):
    """SUS + 만장일치 — 정답 노출 없이 '의도와 어긋난 점'을 짚는 톤 기대."""
    code = (
        "n = int(input())\n"
        "if n == 0: print(1)\n"
        "elif n == 1: print(1)\n"
        "elif n == 5: print(120)\n"
        "elif n == 12: print(479001600)\n"
        "else: print(0)\n"
    )
    rec = await _run(
        name="tutor_sus_hardcoded_factorial",
        problem=factorial_problem,
        code=code,
        verdict="SUS",
        votes=[
            _vote("Melchior", "SUS", False, 1.0, "if/elif 매핑"),
            _vote("Balthasar", "SUS", False, 0.85, "정답을 직접 매핑"),
            _vote("Casper", "SUS", False, 0.9, "알고리즘 부재"),
        ],
        test_results=[_ok(i) for i in range(1, 5)],
        notes="SUS unanimous — 정답 노출 금지 + 학생이 다시 시도할 방향만 제시 기대",
    )
    tutor_recorder.write(rec)
    assert rec.message
    # 가장 흔한 누설 패턴: 정공법 코드 스니펫을 그대로 보여주면 안 됨.
    assert "for i in range(1, n + 1)" not in rec.message, (
        "튜터가 정답 스니펫을 그대로 노출했음"
    )


async def test_tutor_wa_off_by_one(
    tutor_recorder: LiveTutorRecorder, factorial_problem: Problem
):
    """WA → votes=None — '왜 답이 안 맞는지' 케이스 입력/기대/실제로 추론하는 톤 기대."""
    code = "n = int(input())\nprint(n + 1)  # 잘못된 식\n"
    rec = await _run(
        name="tutor_wa_off_by_one",
        problem=factorial_problem,
        code=code,
        verdict="SUS",
        votes=None,
        test_results=[
            _ok(1, ms=11),     # 0+1 == 1 → 우연히 통과
            _wa(2, "2"),       # 1+1=2, expected 1
            _wa(3, "6"),       # 5+1=6, expected 120
            _wa(4, "13"),      # 12+1=13, expected 479001600
        ],
        notes="WA — votes 없음, 케이스별 입력/기대/실제로 추론하는 톤 기대",
    )
    tutor_recorder.write(rec)
    assert rec.message


async def test_tutor_re_zerodiv(
    tutor_recorder: LiveTutorRecorder, factorial_problem: Problem
):
    """RE → votes=None — '실패 원인을 추적'하는 톤 기대."""
    code = "n = int(input())\nprint(1 / 0)\n"
    rec = await _run(
        name="tutor_re_zerodiv",
        problem=factorial_problem,
        code=code,
        verdict="SUS",
        votes=None,
        test_results=[
            _re(i, "ZeroDivisionError: division by zero")
            for i in range(1, 5)
        ],
        notes="RE — ZeroDivision으로 죽음. 어디서 0으로 나누는지 짚어주길 기대",
    )
    tutor_recorder.write(rec)
    assert rec.message
