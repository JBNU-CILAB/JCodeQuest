from collections import Counter
from dataclasses import dataclass

from langchain_ollama import ChatOllama

from ..schemas import EnsembleResult, JudgeVote, Problem, TestResult
from .prompts import judge_prompt


@dataclass(frozen=True)
class JudgeSpec:
    judge_id: str
    model: str
    persona: str


JUDGES = [
    JudgeSpec("Melchior", "qwen2.5-coder:14b-instruct-q5_K_M", "엄격한 채점관"),
    JudgeSpec("Balthasar", "deepseek-coder-v2:16b-lite-instruct", "코드 리뷰어"),
    JudgeSpec("Casper", "llama3.1:8b-instruct-q5_K_M", "출제자 의도 분석가"),
]


async def _ask(
    spec: JudgeSpec,
    problem: Problem,
    code: str,
    results: list[TestResult],
    base_url: str | None,
) -> JudgeVote:
    llm = ChatOllama(model=spec.model, temperature=0, format="json", base_url=base_url)
    chain = judge_prompt | llm.with_structured_output(JudgeVote, method="json_mode")
    r = problem.intent_rubric
    passed = sum(x.passed for x in results)
    out: JudgeVote = await chain.ainvoke(
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
    return out.model_copy(update={"judge_id": spec.judge_id})


async def vote(
    problem: Problem,
    code: str,
    test_results: list[TestResult],
    base_url: str | None = None,
) -> EnsembleResult:
    votes = [await _ask(s, problem, code, test_results, base_url) for s in JUDGES]
    top, n = Counter(v.verdict for v in votes).most_common(1)[0]
    mode = "unanimous" if n == len(votes) else "majority"
    return EnsembleResult(final_verdict=top, mode=mode, votes=votes)
