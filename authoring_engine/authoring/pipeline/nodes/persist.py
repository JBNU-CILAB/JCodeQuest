from ...config import ensure_backend_on_path
from ...schemas import AuthoringState


def persist_approved(state: AuthoringState) -> dict:
    """solver_passed된 문제를 status='approved'로 DB에 저장한다."""
    ensure_backend_on_path()
    from src.schemas import IntentRubric, Problem, TestCase  # type: ignore[import]
    from src.storage.db import get_session  # type: ignore[import]
    from src.storage.problems import create_problem  # type: ignore[import]

    saved_ids: list[int] = list(state.get("saved_problem_ids", []))
    errors: list[str] = list(state.get("errors", []))
    updated: list[dict] = []

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
            # id=0 은 create_problem이 무시하고 DB가 auto-assign한다
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
            with get_session() as session:
                pid = create_problem(session, problem, status="approved")
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
