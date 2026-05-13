from dataclasses import dataclass

from jcq_shared.schemas import EnsembleResult, JudgeVote, JudgeVotePartial, Problem, TestResult
from langchain_ollama import ChatOllama

from .prompts import judge_prompt

# 2/3 이상 AC면 AC. 투표는 binary(AC|SUS)이고 판사 3명 → 분포는
# 3-0 / 2-1 / 1-2 / 0-3 네 가지뿐이라 이 임계 하나로 mode까지 결정됨.
AC_RATIO_THRESHOLD = 2 / 3


@dataclass(frozen=True)
class JudgeSpec:
    judge_id: str
    model: str
    persona: str


JUDGES = [
    JudgeSpec("Melchior", "qwen2.5-coder:14b-instruct-q5_K_M", "엄격한 채점관"),
    JudgeSpec("Balthasar", "deepseek-coder-v2:lite", "코드 리뷰어"),
    JudgeSpec("Casper", "llama3.1:8b", "출제자 의도 분석가"),
]


async def _ask(
    spec: JudgeSpec,
    problem: Problem,
    code: str,
    results: list[TestResult],
    base_url: str | None,
) -> JudgeVote:
    llm = ChatOllama(
        model=spec.model,
        temperature=0,
        format="json",
        base_url=base_url,
        num_ctx=8192,
        keep_alive="30m",
    )
    chain = judge_prompt | llm.with_structured_output(JudgeVotePartial, method="json_mode")
    r = problem.intent_rubric
    passed = sum(x.passed for x in results)
    partial: JudgeVotePartial = await chain.ainvoke(
        {
            "persona": spec.persona,
            "title": problem.title,
            "statement": problem.statement,
            "expected_approach": r.expected_approach,
            "expected_complexity": r.expected_complexity,
            "must_handle": ", ".join(r.must_handle) or "(없음)",
            "forbidden_patterns": ", ".join(r.forbidden_patterns) or "(없음)",
            "key_insight": r.key_insight,
            "test_summary": f"통과 {passed}/{len(results)}" if results else "테스트 결과 없음",
            "code": code,
        }
    )
    return JudgeVote(judge_id=spec.judge_id, **partial.model_dump())


async def vote(
    problem: Problem,
    code: str,
    test_results: list[TestResult],
    base_url: str | None = None,
) -> EnsembleResult:
    votes = [await _ask(s, problem, code, test_results, base_url) for s in JUDGES]
    n_ac = sum(1 for v in votes if v.verdict == "AC")
    total = len(votes)
    final = "AC" if n_ac / total >= AC_RATIO_THRESHOLD else "SUS"
    mode = "unanimous" if n_ac in (0, total) else "majority"
    return EnsembleResult(final_verdict=final, mode=mode, votes=votes)
