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
