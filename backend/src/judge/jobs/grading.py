import asyncio
import logging
import os

from ...events import SubmissionEventBroker
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


def _skip_ensemble() -> bool:
    """JCQ_SKIP_ENSEMBLE=1 → 3-LLM 앙상블 단계만 건너뛰고
    "샌드박스 전체 테스트 통과 = AC"로 직행. 샌드박스 채점은 동일하게 동작.
    Ollama 미설치/오프라인 개발 환경 편의용. 프로덕션에서는 절대 켜지 말 것."""
    return (os.getenv("JCQ_SKIP_ENSEMBLE", "") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


async def grade_submission(
    submission_id: int,
    problem: Problem,
    code: str,
    *,
    events: SubmissionEventBroker | None = None,
) -> None:
    base_url = os.getenv("OLLAMA_BASE_URL")
    skip_ensemble = _skip_ensemble()

    with get_session() as s:
        set_status(s, submission_id, "running")
    if events is not None:
        events.notify(submission_id)

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
            if skip_ensemble:
                log.warning(
                    "submission %d: JCQ_SKIP_ENSEMBLE=1 — bypassing 3-LLM vote, "
                    "treating all-tests-passed as AC (DEV ONLY)",
                    submission_id,
                )
                verdict = "AC"
            else:
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
        if events is not None:
            events.notify(submission_id)
    except Exception:
        log.exception("grading failed for submission %d", submission_id)
        with get_session() as s:
            set_status(s, submission_id, "failed")
        if events is not None:
            events.notify(submission_id)
        raise
