import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama

from ...config import (
    COMPARE_MODEL,
    ENSEMBLE_NUM_CTX,
    ENSEMBLE_TEMPERATURE,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
)
from ...schemas import AuthoringState
from ..prompts import COMPARE_SYSTEM, COMPARE_USER

# 단일 judge — 비교 평가는 순수 기록 목적이라 3-judge 앙상블까지 돌릴 필요 없음. (env로 설정)
_COMPARE_MODEL = COMPARE_MODEL


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
        return {
            "comparison_hallucination": round(
                _clamp01(float(result.get("hallucination_score", 0.0))), 3
            ),
            "comparison_intent_similarity": round(
                _clamp01(float(result.get("intent_similarity", 0.0))), 3
            ),
            "comparison_difficulty_similarity": round(
                _clamp01(float(result.get("difficulty_similarity", 0.0))), 3
            ),
            "comparison_rationale": f"[{judge_id}] {result.get('rationale', '')}",
            "comparison_error": "",
        }
    except Exception as exc:
        return {
            "comparison_hallucination": None,
            "comparison_intent_similarity": None,
            "comparison_difficulty_similarity": None,
            "comparison_rationale": "",
            "comparison_error": f"[{judge_id}] {exc}",
        }


def compare_to_original(state: AuthoringState) -> dict:
    """3-judge 평가(judge_candidates + solve_candidates)가 모두 끝난 후보에 한해
    단일 judge가 원본과 변형을 비교한 3축 수치를 기록한다. 게이트가 아니다 —
    persist는 이 결과를 보지 않고 solver_passed로만 판단한다.
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
