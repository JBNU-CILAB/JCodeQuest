import asyncio
import logging
import os

from ...schemas import Problem, TestResult
from ...storage import get_session
from ...storage.submissions import save_grading, set_status
from ..ensemble import vote
from ..sandbox import run_all_tests

log = logging.getLogger(__name__)


def _efficiency_multiplier(
    results: list[TestResult], time_limit_ms: int, memory_limit_mb: int
) -> float:
    if not results:
        return 1.0
    max_time = max(r.elapsed_ms for r in results)
    max_mem = max(r.peak_memory_kb for r in results)
    mem_limit_kb = memory_limit_mb * 1024
    t_pct = min(1.0, max_time / max(1, time_limit_ms))
    m_pct = min(1.0, max_mem / max(1, mem_limit_kb))
    eff = 0.5 * (1 - t_pct) + 0.5 * (1 - m_pct)
    return 0.5 + 0.5 * eff


async def grade_submission(
    submission_id: int, problem: Problem, code: str
) -> None:
    base_url = os.getenv("OLLAMA_BASE_URL")

    with get_session() as s:
        set_status(s, submission_id, "running")

    try:
        test_results = await asyncio.to_thread(
            run_all_tests,
            code,
            problem.test_cases,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_mb=problem.memory_limit_mb,
        )

        all_passed = bool(test_results) and all(r.passed for r in test_results)
        ensemble = None
        verdict: str = "SUS"
        if all_passed:
            ensemble = await vote(problem, code, test_results, base_url=base_url)
            verdict = ensemble.final_verdict

        points = 0
        if verdict == "AC":
            mul = _efficiency_multiplier(
                test_results, problem.time_limit_ms, problem.memory_limit_mb
            )
            points = int(problem.points * mul)

        with get_session() as s:
            save_grading(
                s,
                submission_id,
                final_verdict=verdict,
                test_results=test_results,
                ensemble=ensemble,
                points_awarded=points,
            )
    except Exception:
        log.exception("grading failed for submission %d", submission_id)
        with get_session() as s:
            set_status(s, submission_id, "failed")
        raise
