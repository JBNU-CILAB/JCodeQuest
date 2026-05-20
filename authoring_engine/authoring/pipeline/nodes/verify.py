import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from ...backend_client import sandbox_run
from ...config import (
    AUTHOR_MODEL,
    AUTHOR_NUM_CTX,
    AUTHOR_RETRY_TEMPERATURE,
    MAX_AUTHOR_RETRIES,
    OLLAMA_BASE_URL,
    PERF_RATIO,
)
from ...schemas import AuthoringState
from ..prompts import SOLUTION_SYSTEM, SOLUTION_USER

_MIN_TEST_CASES = 4


def _run_verification(candidate: dict) -> tuple[list[dict], bool, str]:
    """reference_code를 각 test_input에 sandbox 실행해 expected_stdout 채움.

    Returns (test_cases, all_ok, error_message)
    """
    reference_code = candidate.get("reference_code", "")
    test_inputs = candidate.get("test_inputs", [])
    time_limit_ms = candidate["time_limit_ms"]
    memory_limit_mb = candidate["memory_limit_mb"]

    if not reference_code:
        return [], False, "reference_code가 비어있음"
    if len(test_inputs) < _MIN_TEST_CASES:
        return [], False, f"test_inputs가 {len(test_inputs)}개로 부족 (최소 {_MIN_TEST_CASES}개)"

    test_cases: list[dict] = []
    for ti in test_inputs:
        stdin = ti.get("stdin", "")
        if stdin and not stdin.endswith("\n"):
            stdin += "\n"

        result = sandbox_run(
            reference_code,
            stdin,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )

        if result.status != "OK":
            return (
                [],
                False,
                f"ordinal={ti.get('ordinal', '?')}: {result.status} — {result.stderr[:300]}",
            )

        limit = time_limit_ms * PERF_RATIO
        if result.elapsed_ms > limit:
            return (
                [],
                False,
                f"ordinal={ti.get('ordinal', '?')}: 너무 느림 ({result.elapsed_ms}ms > {limit}ms)",
            )

        test_cases.append(
            {
                "ordinal": ti.get("ordinal", len(test_cases) + 1),
                "stdin": stdin,
                "expected_stdout": result.stdout.rstrip(),
                "is_sample": ti.get("is_sample", False),
            }
        )

    return test_cases, True, ""


def _regenerate_solution(candidate: dict, llm: ChatOllama) -> tuple[str, list] | tuple[None, None]:
    """author_solution 노드 로직을 재실행해 reference_code + test_inputs 재생성."""
    rubric = candidate.get("intent_rubric", {})
    try:
        resp = llm.invoke(
            [
                SystemMessage(content=SOLUTION_SYSTEM),
                HumanMessage(
                    content=SOLUTION_USER.format(
                        title=candidate.get("title", ""),
                        statement=candidate.get("statement", ""),
                        expected_approach=rubric.get("expected_approach", ""),
                        key_insight=rubric.get("key_insight", ""),
                        expected_complexity=rubric.get("expected_complexity", ""),
                        must_handle=", ".join(rubric.get("must_handle", [])),
                        forbidden_patterns=", ".join(rubric.get("forbidden_patterns", [])),
                        time_limit_ms=candidate["time_limit_ms"],
                        memory_limit_mb=candidate["memory_limit_mb"],
                    )
                ),
            ]
        )
        text = resp.content.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        sol = json.loads(text.strip())
        return sol.get("reference_code", ""), sol.get("test_inputs", [])
    except Exception:
        return None, None


def verify_candidates(state: AuthoringState) -> dict:
    """각 candidate의 reference_code를 sandbox에서 실행해 expected_stdout을 채운다.

    실패 시 author_solution을 최대 MAX_AUTHOR_RETRIES회 재시도한다.
    재시도는 temperature를 올려 결정론적 반복 실패를 피한다.
    """
    retry_llm = ChatOllama(
        model=AUTHOR_MODEL,
        temperature=AUTHOR_RETRY_TEMPERATURE,
        format="json",
        base_url=OLLAMA_BASE_URL,
        num_ctx=AUTHOR_NUM_CTX,
        keep_alive="30m",
    )

    updated: list[dict] = []
    for c in state["candidates"]:
        c = dict(c)
        test_cases: list[dict] = []
        passed = False
        error = ""

        for attempt in range(MAX_AUTHOR_RETRIES + 1):
            test_cases, passed, error = _run_verification(c)
            if passed:
                c["verify_attempts"] = attempt + 1
                break

            if attempt < MAX_AUTHOR_RETRIES:
                ref_code, test_inputs = _regenerate_solution(c, retry_llm)
                if ref_code:
                    c["reference_code"] = ref_code
                    c["test_inputs"] = test_inputs or c["test_inputs"]
        else:
            c["verify_attempts"] = MAX_AUTHOR_RETRIES + 1

        c["test_cases"] = test_cases
        c["verify_passed"] = passed
        c["verify_error"] = error
        updated.append(c)

    return {"candidates": updated}
