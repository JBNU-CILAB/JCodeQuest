from datetime import datetime, timezone

from jcq_shared.schemas import IntentRubric, Problem, TestCase

from ...backend_client import create_problem
from ...config import (
    RAG_ENABLED,
    RAG_LEVEL_WINDOW,
    RAG_MIN_JUDGE_SCORE,
    RAG_MMR_LAMBDA,
    RAG_TOP_K,
)
from ...schemas import AuthoringState


def _iso_week_of(dt: datetime) -> str:
    """backend의 iso_week_of와 동일 — HTTP를 거치지 않고도 같은 라벨을 생성하기 위해 중복 정의.
    실제 저장 시점에 backend가 비어 있는 경우 다시 채우므로 일관성 보장."""
    y, w, _ = dt.isocalendar()
    return f"{y:04d}-W{w:02d}"


def persist_approved(state: AuthoringState) -> dict:
    """solver_passed된 변형 후보를 backend /internal/problems API로 저장한다."""
    saved_ids: list[int] = list(state.get("saved_problem_ids", []))
    errors: list[str] = list(state.get("errors", []))
    updated: list[dict] = []

    parent_id = state.get("original_problem_id")
    trace_id = state.get("langsmith_trace_id")
    # 같은 배치(같은 파이프라인 실행)의 모든 변종은 한 주차로 묶는다 — 파이프라인이
    # 자정/주차 경계를 가로지르더라도 일관된 라벨을 갖도록 노드 진입 시점에 한 번 계산.
    issued_week = _iso_week_of(datetime.now(timezone.utc))

    # RAG 메타는 배치 단위(retrieve_exemplars가 실행당 한 번 고른 exemplars) — 같은
    # 실행의 모든 변종이 같은 참고 모범문제를 grounding으로 썼으므로 공통으로 기록한다.
    # enabled=True인데 exemplars=[]면 'RAG는 돌았으나 빈 코퍼스/폴백'을 의미(RAG off와 구분).
    exemplars = state.get("exemplars") or []
    rag_meta = {
        "enabled": RAG_ENABLED,
        "top_k": RAG_TOP_K,
        "mmr_lambda": RAG_MMR_LAMBDA,
        "level_window": RAG_LEVEL_WINDOW,
        "min_judge_score": RAG_MIN_JUDGE_SCORE,
        "exemplars": [
            {"id": e.get("id"), "title": e.get("title")} for e in exemplars
        ],
    }

    for c in state["candidates"]:
        c = dict(c)
        # persist 게이트: solver(풀이 가능) + discrimination(테스트 변별력) + compare(환각/의도).
        # 신규(변별력·compare) 게이트는 .get(..., True) 기본값이라 해당 기능을 끄면 기존 동작 유지.
        if not (
            c.get("solver_passed")
            and c.get("discrimination_passed", True)
            and c.get("compare_passed", True)
        ):
            updated.append(c)
            continue

        try:
            rubric = IntentRubric.model_validate(c["intent_rubric"])
            test_cases = [
                TestCase(
                    ordinal=tc["ordinal"],
                    stdin=tc["stdin"],
                    expected_stdout=tc["expected_stdout"],
                    is_sample=tc.get("is_sample", False),
                )
                for tc in c["test_cases"]
            ]
            # id=0은 backend가 무시하고 auto-assign
            problem = Problem(
                id=0,
                title=c["title"],
                statement=c["statement"],
                category=c["category"],
                level=c["level"],
                points=c["points"],
                time_limit_ms=c["time_limit_ms"],
                memory_limit_mb=c["memory_limit_mb"],
                reference_code=c["reference_code"],
                intent_rubric=rubric,
                test_cases=test_cases,
            )
            authoring_meta = {
                "candidate_index": c.get("index"),
                "judge_score": c.get("judge_score"),
                "judge_scores": c.get("judge_scores") or [],
                "judge_passed": c.get("judge_passed"),
                "judge_rationale": c.get("judge_rationale"),
                "judge_issues": c.get("judge_issues") or [],
                "solver_results": c.get("solver_results") or [],
                "solver_passed": c.get("solver_passed"),
                "verify_passed": c.get("verify_passed"),
                "verify_error": c.get("verify_error"),
                "verify_attempts": c.get("verify_attempts"),
                # attack_candidates 노드 — 테스트 변별력 게이트.
                "discrimination": {
                    "score": c.get("discrimination_score"),
                    "passed": c.get("discrimination_passed"),
                    "attacks": c.get("attack_results") or [],
                },
                # compare_to_original 노드 — 환각/의도유사도는 게이트, 난이도는 기록.
                "comparison": {
                    "hallucination_score": c.get("comparison_hallucination"),
                    "intent_similarity": c.get("comparison_intent_similarity"),
                    "difficulty_similarity": c.get("comparison_difficulty_similarity"),
                    "rationale": c.get("comparison_rationale") or "",
                    "error": c.get("comparison_error") or "",
                    "passed": c.get("compare_passed"),
                },
                # 신규성 검사 결과 — 어떤 형제와 얼마나 유사했는지(게이트 통과분).
                "novelty": {
                    "max_similarity": c.get("novelty_max_similarity"),
                    "closest_id": c.get("novelty_closest_id"),
                    "attempts": c.get("novelty_attempts"),
                },
                # RAG exemplar 검색 결과 — 이 변종이 어떤 모범문제를 grounding으로 참고했는지.
                "rag": rag_meta,
                # 사후에 trace만 봐도 '몇 주차 출제분'인지 확인 가능하도록 함께 저장.
                "issued_iso_week": issued_week,
            }
            pid = create_problem(
                problem,
                status="approved",
                parent_id=parent_id,
                langsmith_trace_id=trace_id,
                authoring_meta=authoring_meta,
                iso_week=issued_week,
                embedding=c.get("embedding"),
            )
            c["saved_id"] = pid
            saved_ids.append(pid)
        except Exception as exc:
            errors.append(f"persist 실패 '{c.get('title', '?')}': {exc}")

        updated.append(c)

    return {
        "candidates": updated,
        "saved_problem_ids": saved_ids,
        "errors": errors,
    }
