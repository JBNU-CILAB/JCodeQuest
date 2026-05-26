import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama

from ...config import (
    COMPARE_GATE_ENABLED,
    COMPARE_MAX_HALLUCINATION,
    COMPARE_MIN_INTENT_SIM,
    COMPARE_MODEL,
    ENSEMBLE_NUM_CTX,
    ENSEMBLE_TEMPERATURE,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
)
from ...schemas import AuthoringState
from ..prompts import COMPARE_SYSTEM, COMPARE_USER

# 단일 judge — 비교 평가는 3-judge·solver·변별력을 이미 통과한 후보를 한 번 더 거르는
# 보조 게이트라 앙상블까지 돌리지 않는다. 대신 오류 시 fail-open으로 통과시킨다. (env로 설정)
_COMPARE_MODEL = COMPARE_MODEL


def _passes_compare_gate(hallucination: float, intent_similarity: float) -> bool:
    """환각이 임계 이하 + 의도유사도가 임계 이상이면 통과. 난이도는 게이트에서 제외."""
    if not COMPARE_GATE_ENABLED:
        return True
    return (
        hallucination <= COMPARE_MAX_HALLUCINATION
        and intent_similarity >= COMPARE_MIN_INTENT_SIM
    )


def _parse_compare_response(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return json.loads(text.strip())


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _summarize_test_cases(test_cases: list[dict]) -> str:
    if not test_cases:
        return "(없음)"
    lines = [
        f"케이스 {tc.get('ordinal', i+1)} "
        f"({'sample' if tc.get('is_sample') else 'hidden'}): "
        f"stdin={repr(tc.get('stdin', '')[:60])}"
        for i, tc in enumerate(test_cases)
    ]
    return "\n".join(lines)


def _compare_one(original: dict, candidate: dict) -> dict:
    orig_rubric = original.get("intent_rubric") or {}
    cand_rubric = candidate.get("intent_rubric") or {}

    judge_id, model = _COMPARE_MODEL
    llm = ChatOllama(
        model=model,
        temperature=ENSEMBLE_TEMPERATURE,
        format="json",
        base_url=OLLAMA_BASE_URL,
        num_ctx=ENSEMBLE_NUM_CTX,
        keep_alive=OLLAMA_KEEP_ALIVE,
    )

    try:
        resp = llm.invoke(
            [
                SystemMessage(content=COMPARE_SYSTEM),
                HumanMessage(
                    content=COMPARE_USER.format(
                        orig_title=original.get("title", ""),
                        orig_category=original.get("category", ""),
                        orig_level=original.get("level", ""),
                        orig_time_limit_ms=original.get("time_limit_ms", ""),
                        orig_memory_limit_mb=original.get("memory_limit_mb", ""),
                        orig_statement=original.get("statement", ""),
                        orig_expected_approach=orig_rubric.get("expected_approach", ""),
                        orig_expected_complexity=orig_rubric.get("expected_complexity", ""),
                        orig_key_insight=orig_rubric.get("key_insight", ""),
                        orig_must_handle=", ".join(orig_rubric.get("must_handle", [])),
                        orig_forbidden_patterns=", ".join(
                            orig_rubric.get("forbidden_patterns", [])
                        ),
                        cand_title=candidate.get("title", ""),
                        cand_category=candidate.get("category", ""),
                        cand_level=candidate.get("level", ""),
                        cand_time_limit_ms=candidate.get("time_limit_ms", ""),
                        cand_memory_limit_mb=candidate.get("memory_limit_mb", ""),
                        cand_statement=candidate.get("statement", ""),
                        cand_expected_approach=cand_rubric.get("expected_approach", ""),
                        cand_expected_complexity=cand_rubric.get("expected_complexity", ""),
                        cand_key_insight=cand_rubric.get("key_insight", ""),
                        cand_must_handle=", ".join(cand_rubric.get("must_handle", [])),
                        cand_forbidden_patterns=", ".join(
                            cand_rubric.get("forbidden_patterns", [])
                        ),
                        cand_test_cases_summary=_summarize_test_cases(
                            candidate.get("test_cases", [])
                        ),
                    )
                ),
            ],
            config=RunnableConfig(run_name=f"compare_to_original/{judge_id}"),
        )
        result = _parse_compare_response(resp.content)
        hallucination = _clamp01(float(result.get("hallucination_score", 0.0)))
        intent_similarity = _clamp01(float(result.get("intent_similarity", 0.0)))
        difficulty_similarity = _clamp01(float(result.get("difficulty_similarity", 0.0)))
        return {
            "comparison_hallucination": round(hallucination, 3),
            "comparison_intent_similarity": round(intent_similarity, 3),
            "comparison_difficulty_similarity": round(difficulty_similarity, 3),
            "comparison_rationale": f"[{judge_id}] {result.get('rationale', '')}",
            "comparison_error": "",
            "compare_passed": _passes_compare_gate(hallucination, intent_similarity),
        }
    except Exception as exc:
        # 단일 judge 오류는 노이즈로 보고 통과시킨다(fail-open) — 앞선 게이트를 이미 통과함.
        return {
            "comparison_hallucination": None,
            "comparison_intent_similarity": None,
            "comparison_difficulty_similarity": None,
            "comparison_rationale": "",
            "comparison_error": f"[{judge_id}] {exc}",
            "compare_passed": True,
        }


def compare_to_original(state: AuthoringState) -> dict:
    """앞선 단계(judge/solve/attack)를 통과한 후보에 한해 단일 judge가 원본과 변형을
    비교한 3축 수치를 기록하고, 환각·의도유사도를 보조 게이트로 적용한다.

    compare_passed는 persist 게이트의 한 축이다(난이도 유사도는 기록만, 게이트 제외).
    단일 judge라 오류 시 fail-open이며 JCQ_COMPARE_GATE_ENABLED=0이면 항상 통과로 둔다.
    """
    original = state.get("original_problem")
    if not original:
        return {"candidates": list(state.get("candidates", []))}

    updated: list[dict] = []
    for c in state.get("candidates", []):
        c = dict(c)
        # solver_results가 있으면 solve_candidates 까지 진입했다는 뜻 → 직전 단계가 모두 완료.
        if c.get("solver_results"):
            c.update(_compare_one(original, c))
        updated.append(c)
    return {"candidates": updated}
