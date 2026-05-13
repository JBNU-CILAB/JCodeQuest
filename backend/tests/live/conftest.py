"""실제 Ollama에 붙는 라이브 LLM 테스트.

기본 동작:
- 환경변수 `JCQ_RUN_LIVE_LLM=1`이 켜져 있고
- `OLLAMA_BASE_URL`(또는 기본값 http://localhost:11434)이 살아있을 때만 수집됨.
- 그 외엔 모듈 단위로 skip → 일반 `pytest`는 영향 없음.

기록물:
- `tests/artifacts/live_llm_<timestamp>.jsonl` — 시나리오별 raw 레코드 (즉시 flush)
- `tests/artifacts/live_llm_<timestamp>.md` — 사람이 읽는 요약 표 + 판사 의견 상세
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# 채점 엔진 모듈(judge.sandbox/judge.ensemble)이 backend venv에는 설치돼 있지 않아
# 라이브 채점 슈트에서 직접 import하려면 judge_engine/을 sys.path에 끼워야 한다.
_JUDGE_ENGINE = Path(__file__).resolve().parents[3] / "judge_engine"
if _JUDGE_ENGINE.is_dir() and str(_JUDGE_ENGINE) not in sys.path:
    sys.path.insert(0, str(_JUDGE_ENGINE))
from typing import Any

import pytest

from src.schemas import IntentRubric, Problem, TestCase

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"


def _ollama_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def _ollama_alive(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as r:
            if r.status != 200:
                return False, f"HTTP {r.status}"
            data = json.loads(r.read().decode("utf-8"))
            tags = [m.get("name", "") for m in data.get("models", [])]
            return True, ", ".join(tags) or "(no models)"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return False, str(e)


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """게이팅:
    - JCQ_RUN_LIVE_LLM=1 아니면 live/* 전부 skip
    - Ollama 죽으면 ensemble 슈트만 skip (튜터는 OpenAI라 무관)
    - OPENAI_API_KEY 없으면 튜터 슈트만 skip
    """
    if os.getenv("JCQ_RUN_LIVE_LLM", "").strip() not in ("1", "true", "yes"):
        skip = pytest.mark.skip(reason="JCQ_RUN_LIVE_LLM=1 필요")
        for item in items:
            if "tests/live/" in str(item.fspath).replace("\\", "/"):
                item.add_marker(skip)
        return

    url = _ollama_url()
    alive, info = _ollama_alive(url)
    if not alive:
        skip_oll = pytest.mark.skip(reason=f"Ollama unreachable @ {url}: {info}")
        for item in items:
            path = str(item.fspath).replace("\\", "/")
            # 튜터는 Ollama 안 씀 — 죽어 있어도 통과 가능
            if "tests/live/" in path and "test_live_tutor" not in path:
                item.add_marker(skip_oll)

    if not os.getenv("OPENAI_API_KEY"):
        skip_oai = pytest.mark.skip(reason="OPENAI_API_KEY 필요")
        for item in items:
            if "test_live_tutor" in str(item.fspath).replace("\\", "/"):
                item.add_marker(skip_oai)


# ────────────────────────── recorder ──────────────────────────


@dataclass
class ScenarioRecord:
    name: str
    expected_verdict: str | None
    code: str
    test_results: list[dict] = field(default_factory=list)
    ensemble: dict | None = None
    actual_verdict: str | None = None
    elapsed_s: float = 0.0
    notes: str = ""
    passed_assertion: bool | None = None


class LiveRunRecorder:
    def __init__(self, jsonl_path: Path, md_path: Path, ollama_url: str, models_info: str):
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = jsonl_path
        self.md_path = md_path
        self.ollama_url = ollama_url
        self.models_info = models_info
        self._fp = jsonl_path.open("w", encoding="utf-8")
        self._records: list[ScenarioRecord] = []

    def write(self, rec: ScenarioRecord) -> None:
        self._records.append(rec)
        line = json.dumps(rec.__dict__, ensure_ascii=False, default=str)
        self._fp.write(line + "\n")
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()
        self._render_markdown()

    def _render_markdown(self) -> None:
        lines: list[str] = []
        ts = datetime.now().isoformat(timespec="seconds")
        lines.append(f"# Live LLM Test Run — {ts}\n")
        lines.append(f"- Ollama: `{self.ollama_url}`")
        lines.append(f"- Available models: {self.models_info}")
        lines.append(f"- Records: {len(self._records)}\n")

        # 요약 표
        lines.append("## Summary\n")
        lines.append("| Scenario | Expected | Actual | Mode | Tests | Elapsed | Match |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in self._records:
            mode = (r.ensemble or {}).get("mode") or "-"
            tr_total = len(r.test_results)
            tr_pass = sum(1 for t in r.test_results if t.get("passed"))
            tests_summary = f"{tr_pass}/{tr_total}" if tr_total else "-"
            match = (
                "pass"
                if r.passed_assertion is True
                else "FAIL"
                if r.passed_assertion is False
                else "-"
            )
            lines.append(
                f"| {r.name} | {r.expected_verdict or '-'} | "
                f"{r.actual_verdict or '-'} | {mode} | {tests_summary} | "
                f"{r.elapsed_s:.1f}s | {match} |"
            )
        lines.append("")

        # 상세
        lines.append("## Details\n")
        for r in self._records:
            head = f"### {r.name}"
            if r.passed_assertion is False:
                head += " — UNEXPECTED"
            lines.append(head)
            if r.notes:
                lines.append(f"_{r.notes}_\n")
            lines.append("```python")
            lines.append(r.code.rstrip())
            lines.append("```\n")

            if r.test_results:
                lines.append("**Sandbox results**")
                for t in r.test_results:
                    flag = "ok" if t.get("passed") else "fail"
                    lines.append(
                        f"- #{t.get('ordinal')} `{t.get('status')}` "
                        f"({flag}, {t.get('elapsed_ms')}ms, "
                        f"{t.get('peak_memory_kb')}KB)"
                    )
                lines.append("")

            if r.ensemble:
                lines.append(
                    f"**Ensemble** → `{r.ensemble.get('final_verdict')}` "
                    f"(mode: `{r.ensemble.get('mode')}`)"
                )
                for v in r.ensemble.get("votes", []):
                    lines.append(
                        f"- **{v.get('judge_id')}** → "
                        f"`{v.get('verdict')}` "
                        f"(intent_match={v.get('intent_match')}, "
                        f"conf={v.get('confidence')})\n"
                        f"  > {v.get('rationale')}"
                    )
                lines.append("")
            else:
                lines.append("**Ensemble** — skipped (sandbox 단계 실패로 LLM 미호출)\n")

        self.md_path.write_text("\n".join(lines), encoding="utf-8")


@dataclass
class TutorScenarioRecord:
    name: str
    problem_title: str
    verdict: str
    code: str
    votes: list[dict] | None
    test_results: list[dict]
    model: str
    message: str
    elapsed_s: float
    notes: str = ""


class LiveTutorRecorder:
    def __init__(self, jsonl_path: Path, md_path: Path, model_label: str):
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = jsonl_path
        self.md_path = md_path
        self.model_label = model_label
        self._fp = jsonl_path.open("w", encoding="utf-8")
        self._records: list[TutorScenarioRecord] = []

    def write(self, rec: TutorScenarioRecord) -> None:
        self._records.append(rec)
        self._fp.write(
            json.dumps(rec.__dict__, ensure_ascii=False, default=str) + "\n"
        )
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()
        self._render_markdown()

    def _render_markdown(self) -> None:
        lines: list[str] = []
        ts = datetime.now().isoformat(timespec="seconds")
        lines.append(f"# Live Tutor Run — {ts}\n")
        lines.append(f"- Endpoint: `{self.model_label}`")
        lines.append(f"- Records: {len(self._records)}\n")

        lines.append("## Summary\n")
        lines.append("| Scenario | Verdict | Tests | Elapsed | Length |")
        lines.append("|---|---|---|---|---|")
        for r in self._records:
            tr_total = len(r.test_results)
            tr_pass = sum(1 for t in r.test_results if t.get("passed"))
            tests = f"{tr_pass}/{tr_total}" if tr_total else "-"
            lines.append(
                f"| {r.name} | {r.verdict} | {tests} | "
                f"{r.elapsed_s:.1f}s | {len(r.message)}자 |"
            )
        lines.append("")

        lines.append("## Details\n")
        for r in self._records:
            lines.append(f"### {r.name}")
            if r.notes:
                lines.append(f"_{r.notes}_\n")
            lines.append(f"- **Problem**: {r.problem_title}")
            lines.append(f"- **Verdict**: `{r.verdict}`")
            lines.append(f"- **Model**: `{r.model}`\n")
            lines.append("**Code**")
            lines.append("```python")
            lines.append(r.code.rstrip())
            lines.append("```\n")
            if r.votes:
                lines.append("**Judge votes**")
                for v in r.votes:
                    lines.append(
                        f"- {v.get('judge_id')}: `{v.get('verdict')}` "
                        f"(intent_match={v.get('intent_match')}, "
                        f"conf={v.get('confidence')}) — {v.get('rationale')}"
                    )
                lines.append("")
            else:
                lines.append("_No LLM votes (sandbox-fail path)_\n")
            lines.append("**Test results**")
            for t in r.test_results:
                flag = "ok" if t.get("passed") else "fail"
                extra = ""
                if not t.get("passed"):
                    if t.get("status") == "OK":
                        extra = f" — actual={t.get('actual_stdout')!r}"
                    elif t.get("status") in ("RE", "TLE", "MLE"):
                        e = (t.get("error") or "").strip()[:120]
                        extra = f" — {t.get('status')} {e}"
                lines.append(
                    f"- #{t.get('ordinal')} `{t.get('status')}` ({flag}){extra}"
                )
            lines.append("")
            lines.append("**Tutor message**")
            lines.append("> " + r.message.replace("\n", "\n> "))
            lines.append("")

        self.md_path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture(scope="session")
def tutor_recorder() -> LiveTutorRecorder:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    label = (
        f"{os.getenv('OPENAI_MODEL', 'gpt-4o-mini')} @ "
        f"{os.getenv('OPENAI_BASE_URL', 'api.openai.com')}"
    )
    rec = LiveTutorRecorder(
        jsonl_path=ARTIFACTS_DIR / f"live_tutor_{ts}.jsonl",
        md_path=ARTIFACTS_DIR / f"live_tutor_{ts}.md",
        model_label=label,
    )
    yield rec
    rec.close()
    print(f"\n[live-tutor] artifacts:\n  - {rec.jsonl_path}\n  - {rec.md_path}")


@pytest.fixture(scope="session")
def recorder() -> LiveRunRecorder:
    url = _ollama_url()
    _, models_info = _ollama_alive(url)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rec = LiveRunRecorder(
        jsonl_path=ARTIFACTS_DIR / f"live_llm_{ts}.jsonl",
        md_path=ARTIFACTS_DIR / f"live_llm_{ts}.md",
        ollama_url=url,
        models_info=models_info,
    )
    yield rec
    rec.close()
    print(f"\n[live-llm] artifacts:\n  - {rec.jsonl_path}\n  - {rec.md_path}")


@pytest.fixture(scope="session")
def ollama_url() -> str:
    return _ollama_url()


# ────────────────────── 시나리오용 problem 셋 ──────────────────────


@pytest.fixture(scope="session")
def double_problem() -> Problem:
    """trivial: 입력 n → 2n 출력. 하드코딩 시나리오에는 부적합 (너무 단순)."""
    return Problem(
        id=0,
        title="2배 출력",
        statement="정수 n이 입력되면 2*n을 출력하라.",
        category="basic",
        level="bronze",
        points=100,
        time_limit_ms=1000,
        memory_limit_mb=128,
        reference_code="n=int(input())\nprint(n*2)\n",
        intent_rubric=IntentRubric(
            expected_approach="입력을 정수로 파싱 후 2배",
            expected_complexity="O(1)",
            must_handle=["0", "음수"],
            forbidden_patterns=["하드코딩"],
            key_insight="단순 산술",
            one_line_summary="n*2 출력",
        ),
        test_cases=[
            TestCase(ordinal=1, stdin="3\n", expected_stdout="6", is_sample=True),
            TestCase(ordinal=2, stdin="0\n", expected_stdout="0"),
            TestCase(ordinal=3, stdin="-5\n", expected_stdout="-10"),
        ],
    )


@pytest.fixture(scope="session")
def factorial_problem() -> Problem:
    """판사가 '하드코딩'과 '진짜 알고리즘'을 구분할 수 있을 정도로 비자명한 문제."""
    rubric = IntentRubric(
        expected_approach="1부터 n까지 누적 곱 (또는 재귀)",
        expected_complexity="O(n)",
        must_handle=["0! = 1", "1! = 1", "12! = 479001600"],
        forbidden_patterns=[
            "하드코딩된 if/elif 분기로 특정 입력값에 정답 매핑",
            "특정 테스트 입력만 처리하는 분기",
        ],
        key_insight="0! = 1, n! = n * (n-1)!",
        one_line_summary="팩토리얼 계산",
    )
    return Problem(
        id=0,
        title="팩토리얼",
        statement="정수 n (0 ≤ n ≤ 12)이 입력되면 n!을 출력하라.",
        category="basic",
        level="bronze",
        points=100,
        time_limit_ms=1000,
        memory_limit_mb=128,
        reference_code=(
            "n = int(input())\n"
            "r = 1\n"
            "for i in range(1, n + 1):\n"
            "    r *= i\n"
            "print(r)\n"
        ),
        intent_rubric=rubric,
        test_cases=[
            TestCase(ordinal=1, stdin="0\n", expected_stdout="1", is_sample=True),
            TestCase(ordinal=2, stdin="1\n", expected_stdout="1"),
            TestCase(ordinal=3, stdin="5\n", expected_stdout="120"),
            TestCase(ordinal=4, stdin="12\n", expected_stdout="479001600"),
        ],
    )


@dataclass
class GradeOutcome:
    verdict: str
    test_results: list
    ensemble: Any | None
    elapsed_s: float
