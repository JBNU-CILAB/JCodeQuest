import asyncio
import os

from fastapi import APIRouter, HTTPException

from ..judge.ensemble import vote
from ..judge.sandbox import run_all_tests
from ..schemas import GradeRequest, GradeResponse, TestResult
from ..storage import get_session
from ..storage.problems import get_problem
from ..storage.submissions import (
    MAX_ATTEMPTS,
    attempt_status,
    create_submission,
    save_grading,
)

router = APIRouter(prefix="/grade", tags=["grading"])


def _efficiency_multiplier(
    results: list[TestResult], time_limit_ms: int, memory_limit_mb: int
) -> float:
    """AC일 때 점수에 곱할 0.5 ~ 1.0 가중치.
    가장 느린/무거운 케이스를 기준으로 50%~100% 사이에서 깎는다."""
    if not results:
        return 1.0
    max_time = max(r.elapsed_ms for r in results)
    max_mem = max(r.peak_memory_kb for r in results)
    mem_limit_kb = memory_limit_mb * 1024
    t_pct = min(1.0, max_time / max(1, time_limit_ms))
    m_pct = min(1.0, max_mem / max(1, mem_limit_kb))
    eff = 0.5 * (1 - t_pct) + 0.5 * (1 - m_pct)
    return 0.5 + 0.5 * eff


@router.post("", response_model=GradeResponse)
async def grade(req: GradeRequest) -> GradeResponse:
    base_url = os.getenv("OLLAMA_BASE_URL")

    with get_session() as session:
        problem = get_problem(session, req.problem_id)
        if problem is None:
            raise HTTPException(404, f"problem {req.problem_id} not found")

        status = attempt_status(session, req.user_id, req.problem_id)
        if status.solved:
            raise HTTPException(409, "이미 해결한 문제입니다")
        if status.attempts >= MAX_ATTEMPTS:
            raise HTTPException(
                429, f"최대 제출 횟수({MAX_ATTEMPTS}회) 초과"
            )

        submission_id = create_submission(
            session,
            user_id=req.user_id,
            problem_id=req.problem_id,
            code=req.code,
        )

    # blocking subprocess — 이벤트 루프 막지 않게 thread로
    test_results = await asyncio.to_thread(
        run_all_tests,
        req.code,
        problem.test_cases,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
    )

    # LLM judge는 모든 테스트 통과 시에만 호출. 그 외엔 즉시 SUS.
    all_passed = bool(test_results) and all(r.passed for r in test_results)
    ensemble = None
    final_verdict: str = "SUS"
    if all_passed:
        ensemble = await vote(problem, req.code, test_results, base_url=base_url)
        final_verdict = ensemble.final_verdict

    points = 0
    if final_verdict == "AC":
        mul = _efficiency_multiplier(
            test_results, problem.time_limit_ms, problem.memory_limit_mb
        )
        points = int(problem.points * mul)

    with get_session() as session:
        save_grading(
            session,
            submission_id,
            final_verdict=final_verdict,
            test_results=test_results,
            ensemble=ensemble,
            points_awarded=points,
        )

    return GradeResponse(
        submission_id=submission_id,
        final_verdict=final_verdict,
        test_results=test_results,
        ensemble=ensemble,
        points_awarded=points,
    )
