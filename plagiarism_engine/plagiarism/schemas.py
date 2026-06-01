from typing import TypedDict


class PlagiarismState(TypedDict, total=False):
    problem_id: int
    run_id: str
    submissions: list[dict]    # [{submission_id, user_id, code}] — 유저당 1건(최신 AC)
    problem_ctx: str           # 문제 의도(expected_approach) — 의미 검토 에이전트용
    engine: str                # 사용된 유사도 엔진: "dolos" | "winnow"
    dolos_pairs: list[dict]    # raw: [{a_id,b_id,similarity,longest_fragment,total_overlap,fragments}]
    suspect_pairs: list[dict]  # 임계/top-K 통과 (검토 큐로 올릴 후보)
    flagged_ids: list[int]     # 영속화된 plagiarism_pair id
    errors: list[str]
    # 첫-AC 자동 트리거 모드에서만 사용 — 해당 user 가 한쪽에 포함된 pair 만 통과시켜
    # LLM 에이전트·persist 비용을 새 제출 관련 N건으로 한정. 미설정(또는 0) 시 전체 모드.
    target_user_id: int
