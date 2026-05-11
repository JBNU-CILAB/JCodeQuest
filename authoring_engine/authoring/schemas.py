from typing import TypedDict

from jcq_shared.schemas import ProblemLevel


class CandidateProblem(TypedDict):
    index: int
    category: str
    level: ProblemLevel
    points: int
    time_limit_ms: int
    memory_limit_mb: int
    # draft_problem 출력
    title: str
    statement: str
    intent_rubric: dict
    # author_solution 출력 (expected_stdout 없음)
    reference_code: str
    test_inputs: list[dict]  # [{ordinal, stdin, is_sample}]
    # verify_executes: sandbox 실행으로 expected_stdout 채움
    test_cases: list[dict]   # [{ordinal, stdin, expected_stdout, is_sample}]
    verify_passed: bool
    verify_error: str
    verify_attempts: int
    # judge_quality: 3-judge 품질 투표
    judge_passed: bool
    judge_score: float
    judge_rationale: str
    judge_issues: list[str]
    # solve_problem: Ollama LLM이 직접 문제 풀기
    solver_results: list[dict]  # [{judge_id, verdict, code, rationale}]
    solver_passed: bool
    # persist
    saved_id: int | None


class AuthoringState(TypedDict, total=False):
    original_problem_id: int
    target_count: int
    original_problem: dict | None
    seeds: list[dict]
    candidates: list[CandidateProblem]
    saved_problem_ids: list[int]
    errors: list[str]
    # 서버에서 주입 — persist 단계가 ProblemRow에 함께 기록
    langsmith_trace_id: str
