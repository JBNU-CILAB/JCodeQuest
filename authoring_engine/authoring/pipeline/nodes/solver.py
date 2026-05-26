import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from ...backend_client import sandbox_run
from ...config import (
    ENSEMBLE_MODELS,
    ENSEMBLE_NUM_CTX,
    ENSEMBLE_TEMPERATURE,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    SOLVER_PASS_MIN_AC,
    SOLVER_SAMPLE_LIMIT,
)
from ...llm import make_chat_model
from ...schemas import AuthoringState
from ..prompts import SOLVER_SYSTEM, SOLVER_USER

# 품질 심사와 동일한 3 LLM이 이번엔 문제 풀이자로 참가 (config.ENSEMBLE_MODELS, env로 설정)
_SOLVER_MODELS = ENSEMBLE_MODELS


def _extract_code(text: str) -> str:
    """마크다운 펜스를 제거하고 Python 코드만 추출."""
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _solve_one(
    candidate: dict,
    judge_id: str,
    model: str,
) -> dict:
    """단일 LLM이 문제를 풀고 sandbox에서 검증한다."""
    test_cases = candidate.get("test_cases", [])
    sample_cases = [tc for tc in test_cases if tc.get("is_sample")]

    sample_text_parts = []
    for tc in sample_cases[:SOLVER_SAMPLE_LIMIT]:
        sample_text_parts.append(
            f"입력:\n{tc.get('stdin', '')}\n출력:\n{tc.get('expected_stdout', '')}"
        )
    sample_text = "\n\n".join(sample_text_parts) or "(샘플 없음)"

    llm = make_chat_model(
        model,
        temperature=ENSEMBLE_TEMPERATURE,
        num_ctx=ENSEMBLE_NUM_CTX,
    )

    try:
        resp = llm.invoke(
            [
                SystemMessage(content=SOLVER_SYSTEM),
                HumanMessage(
                    content=SOLVER_USER.format(
                        title=candidate.get("title", ""),
                        statement=candidate.get("statement", ""),
                        sample_cases=sample_text,
                    )
                ),
            ]
        )
        code = _extract_code(resp.content)
    except Exception as exc:
        return {
            "judge_id": judge_id,
            "verdict": "ERROR",
            "code": "",
            "rationale": str(exc),
        }

    time_limit_ms = candidate["time_limit_ms"]
    memory_limit_mb = candidate["memory_limit_mb"]

    passed = 0
    total = len(test_cases)
    for tc in test_cases:
        result = sandbox_run(
            code,
            tc.get("stdin", ""),
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        if result.status == "TLE":
            return {"judge_id": judge_id, "verdict": "TLE", "code": code, "rationale": "TLE"}
        if result.status in ("MLE", "RE"):
            return {
                "judge_id": judge_id,
                "verdict": result.status,
                "code": code,
                "rationale": result.stderr[:200],
            }
        if result.status == "OK" and result.stdout.rstrip() == tc.get("expected_stdout", "").rstrip():
            passed += 1

    verdict = "AC" if (total > 0 and passed == total) else "FAIL"
    return {
        "judge_id": judge_id,
        "verdict": verdict,
        "code": code,
        "rationale": f"{passed}/{total} 케이스 통과",
    }


def solve_candidates(state: AuthoringState) -> dict:
    """judge_passed된 candidate에 대해 Ollama 3-LLM이 직접 문제를 풀어 검증한다.

    SOLVER_PASS_MIN_AC개 이상 AC면 solvable로 판정.
    """
    updated: list[dict] = []
    for c in state["candidates"]:
        c = dict(c)
        if not c.get("judge_passed"):
            updated.append(c)
            continue

        solver_results = [
            _solve_one(c, judge_id, model)
            for judge_id, model in _SOLVER_MODELS
        ]
        n_ac = sum(1 for r in solver_results if r["verdict"] == "AC")
        c["solver_results"] = solver_results
        c["solver_passed"] = n_ac >= SOLVER_PASS_MIN_AC
        updated.append(c)

    return {"candidates": updated}
