import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama

from ...config import JUDGE_PASS_THRESHOLD, OLLAMA_BASE_URL
from ...schemas import AuthoringState
from ..prompts import JUDGE_QUALITY_SYSTEM, JUDGE_QUALITY_USER

# 채점 앙상블과 동일한 3 판사 — 역할은 학생 코드 채점이 아니라 문제 품질 심사
_QUALITY_JUDGES = [
    ("Melchior", "qwen2.5-coder:14b-instruct-q5_K_M"),
    ("Balthasar", "deepseek-coder-v2:lite"),
    ("Casper", "llama3.1:8b"),
]


def _parse_judge_response(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return json.loads(text.strip())


def _judge_one_candidate(candidate: dict) -> dict:
    """3-judge 앙상블로 문제 품질을 투표. 2/3 이상 pass + 평균 score ≥ threshold면 통과."""
    rubric = candidate.get("intent_rubric", {})
    test_cases = candidate.get("test_cases", [])

    tc_lines = [
        f"케이스 {tc.get('ordinal', i+1)} "
        f"({'sample' if tc.get('is_sample') else 'hidden'}): "
        f"stdin={repr(tc.get('stdin', '')[:60])}"
        for i, tc in enumerate(test_cases)
    ]
    tc_summary = "\n".join(tc_lines) or "(없음)"

    votes_passed: list[bool] = []
    votes_score: list[float] = []
    all_issues: list[str] = []
    rationale_parts: list[str] = []

    for judge_id, model in _QUALITY_JUDGES:
        llm = ChatOllama(
            model=model,
            temperature=0,
            format="json",
            base_url=OLLAMA_BASE_URL,
            num_ctx=4096,
            keep_alive="30m",
        )
        try:
            resp = llm.invoke(
                [
                    SystemMessage(content=JUDGE_QUALITY_SYSTEM),
                    HumanMessage(
                        content=JUDGE_QUALITY_USER.format(
                            title=candidate.get("title", ""),
                            statement=candidate.get("statement", ""),
                            expected_approach=rubric.get("expected_approach", ""),
                            expected_complexity=rubric.get("expected_complexity", ""),
                            key_insight=rubric.get("key_insight", ""),
                            must_handle=", ".join(rubric.get("must_handle", [])),
                            forbidden_patterns=", ".join(
                                rubric.get("forbidden_patterns", [])
                            ),
                            test_cases_summary=tc_summary,
                        )
                    ),
                ],
                config=RunnableConfig(run_name=f"judge_quality/{judge_id}"),
            )
            result = _parse_judge_response(resp.content)
            votes_passed.append(bool(result.get("passed", False)))
            votes_score.append(float(result.get("score", 0.0)))
            all_issues.extend(result.get("issues", []))
            rationale_parts.append(f"[{judge_id}] {result.get('rationale', '')}")
        except Exception as exc:
            votes_passed.append(False)
            votes_score.append(0.0)
            all_issues.append(f"[{judge_id}] 오류: {exc}")

    avg_score = sum(votes_score) / len(votes_score) if votes_score else 0.0
    n_passed = sum(votes_passed)
    # 2/3 이상 pass + 평균 score ≥ threshold
    judge_passed = n_passed >= 2 and avg_score >= JUDGE_PASS_THRESHOLD

    return {
        "judge_passed": judge_passed,
        "judge_score": round(avg_score, 3),
        "judge_rationale": " | ".join(rationale_parts),
        "judge_issues": all_issues,
    }


def judge_candidates(state: AuthoringState) -> dict:
    """verify_passed된 candidate만 LLM 품질 심사를 수행한다."""
    updated: list[dict] = []
    for c in state["candidates"]:
        c = dict(c)
        if c.get("verify_passed"):
            c.update(_judge_one_candidate(c))
        updated.append(c)
    return {"candidates": updated}
