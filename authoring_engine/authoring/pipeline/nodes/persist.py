from datetime import datetime, timezone

from jcq_shared.schemas import IntentRubric, Problem, TestCase

from ...backend_client import create_problem
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

    for c in state["candidates"]:
        c = dict(c)
        if not c.get("solver_passed"):
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
                "judge_passed": c.get("judge_passed"),
                "judge_rationale": c.get("judge_rationale"),
                "judge_issues": c.get("judge_issues") or [],
                "solver_results": c.get("solver_results") or [],
                "solver_passed": c.get("solver_passed"),
                "verify_passed": c.get("verify_passed"),
                "verify_error": c.get("verify_error"),
                "verify_attempts": c.get("verify_attempts"),
                # compare_to_original 노드 — 순수 기록 (게이트 아님)
                "comparison": {
                    "hallucination_score": c.get("comparison_hallucination"),
                    "intent_similarity": c.get("comparison_intent_similarity"),
                    "difficulty_similarity": c.get("comparison_difficulty_similarity"),
                    "rationale": c.get("comparison_rationale") or "",
                    "error": c.get("comparison_error") or "",
                },
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
