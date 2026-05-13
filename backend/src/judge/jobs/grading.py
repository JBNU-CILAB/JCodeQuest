"""채점 결과 webhook을 받아 DB·SSE broker에 반영하는 헬퍼.

이전엔 백엔드 내부 워커가 직접 채점을 돌렸지만, 큐가 judge_engine으로 이전된 뒤로는
판정 자체는 judge_engine이 수행하고 backend는 이 헬퍼를 통해 결과만 영속화한다.
"""
from __future__ import annotations

import logging

from ...events import SubmissionEventBroker
from ...schemas import GradeEvent, TestResult
from ...storage import get_session
from ...storage.problems import get_problem
from ...storage.submissions import save_grading, set_status

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


def apply_grading_event(
    event: GradeEvent,
    *,
    events: SubmissionEventBroker | None = None,
) -> None:
    """judge_engine webhook을 DB에 반영.

    running: status만 갱신
    done:    test_results/ensemble 저장, AC면 points*efficiency 가산 (첫 AC 한정)
    failed:  status='failed' 마킹
    """
    sid = event.submission_id

    if event.event == "running":
        with get_session() as s:
            set_status(s, sid, "running")
        if events is not None:
            events.notify(sid)
        return

    if event.event == "failed":
        log.warning("grade failed submission=%d err=%s", sid, event.error)
        with get_session() as s:
            set_status(s, sid, "failed")
        if events is not None:
            events.notify(sid)
        return

    # event == "done"
    test_results = event.test_results or []
    ensemble = event.ensemble
    all_passed = bool(event.all_passed)

    verdict: str = "SUS"
    if all_passed and ensemble is not None:
        verdict = ensemble.final_verdict

    with get_session() as s:
        # 효율 가산점은 problem의 제한값이 필요 — submission으로부터 problem 조회.
        # judge_engine 페이로드에는 problem 전체가 빠져있으므로 DB에서 재조회.
        from ...storage.submissions import get_submission

        sub = get_submission(s, sid)
        points = 0
        if sub is not None and verdict == "AC":
            problem = get_problem(s, sub.problem_id)
            if problem is not None:
                mul = _efficiency_multiplier(
                    test_results, problem.time_limit_ms, problem.memory_limit_mb
                )
                points = int(problem.points * mul)

        save_grading(
            s,
            sid,
            final_verdict=verdict,
            test_results=test_results,
            ensemble=ensemble,
            points_awarded=points,
        )

    if events is not None:
        events.notify(sid)
