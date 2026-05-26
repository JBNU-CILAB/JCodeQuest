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
    # novelty_check: 카테고리 형제 대비 임베딩 신규성 검사 (generate 내부 루프)
    novelty_passed: bool
    novelty_max_similarity: float
    novelty_closest_id: int | None
    novelty_attempts: int
    # 신규성 통과 draft의 임베딩 — persist가 ProblemRow.embedding으로 저장 (재계산 방지)
    embedding: list[float] | None
    # author_solution 출력 (expected_stdout 없음)
    reference_code: str
    test_inputs: list[dict]  # [{ordinal, stdin, is_sample}]
    # verify_executes: sandbox 실행으로 expected_stdout 채움
    test_cases: list[dict]   # [{ordinal, stdin, expected_stdout, is_sample}]
    verify_passed: bool
    verify_error: str
    verify_attempts: int
    # judge_quality: 3-judge 품질 투표. judge_score는 판사들 점수의 중앙값(이상치에 강건).
    judge_passed: bool
    judge_score: float
    judge_scores: list[float]  # per-judge 점수 (중앙값 산출 근거, 메타 기록용)
    judge_rationale: str
    judge_issues: list[str]
    # solve_problem: Ollama LLM이 직접 문제 풀기
    solver_results: list[dict]  # [{judge_id, verdict, code, rationale}]
    solver_passed: bool
    # attack_candidates: 결함을 심은 공격 풀이가 테스트에 걸리는지(변별력) 검사
    attack_results: list[dict]  # [{strategy, verdict, rejected, code, rationale}]
    discrimination_score: float  # rejected / valid_attacks
    discrimination_passed: bool
    # compare_to_original: 단일 judge가 원본과 변형을 비교한 3축 수치(환각/의도/난이도).
    # compare_passed는 환각·의도유사도 임계로 판정하는 게이트 결과(난이도는 기록만).
    comparison_hallucination: float
    comparison_intent_similarity: float
    comparison_difficulty_similarity: float
    comparison_rationale: str
    comparison_error: str
    compare_passed: bool
    # persist
    saved_id: int | None


class AuthoringState(TypedDict, total=False):
    original_problem_id: int
    target_count: int
    original_problem: dict | None
    seeds: list[dict]
    # 신규성 검사 모집단 — 같은 카테고리 approved 형제의 (id, title, embedding). fetch에서 적재.
    sibling_embeddings: list[dict]
    # RAG exemplar — retrieve_exemplars가 MMR로 고른 모범 사례의 rubric 압축본.
    # 각 항목: {id, title, one_line_summary, expected_approach, key_insight, expected_complexity}.
    # generate가 draft 프롬프트에 주입. 빈 코퍼스/RAG 비활성 시 빈 리스트(예시 없이 생성으로 폴백).
    exemplars: list[dict]
    candidates: list[CandidateProblem]
    saved_problem_ids: list[int]
    errors: list[str]
    # 서버에서 주입 — persist 단계가 ProblemRow에 함께 기록
    langsmith_trace_id: str
