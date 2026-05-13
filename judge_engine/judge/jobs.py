"""채점 잡 — 워커가 큐에서 꺼내 실행하는 단위.

1) backend에 webhook(running)으로 시작 알림
2) 샌드박스로 모든 테스트 케이스 실행
3) 모두 통과 시 3-judge 앙상블 보팅
4) backend에 webhook(done|failed)으로 결과 송신
"""
from __future__ import annotations

import asyncio
import logging
import os

from jcq_shared.schemas import GradeEvent, Problem

from .callback import send_event
from .ensemble import vote
from .sandbox import run_all_tests

log = logging.getLogger(__name__)


async def grade_job(submission_id: int, problem: Problem, code: str) -> None:
    """워커 컨텍스트에서 호출되는 본체. 어떤 예외도 잡아 webhook(failed)로 보고."""
    await send_event(GradeEvent(submission_id=submission_id, event="running"))

    try:
        base_url = os.getenv("OLLAMA_BASE_URL")

        # 샌드박스는 subprocess 기반 동기 — 워커 스레드로 디스패치해 이벤트 루프 미차단
        test_results = await asyncio.to_thread(
            run_all_tests,
            code,
            problem.test_cases,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_mb=problem.memory_limit_mb,
        )

        all_passed = bool(test_results) and all(r.passed for r in test_results)
        ensemble = None
        if all_passed:
            ensemble = await vote(problem, code, test_results, base_url=base_url)

        await send_event(
            GradeEvent(
                submission_id=submission_id,
                event="done",
                test_results=test_results,
                all_passed=all_passed,
                ensemble=ensemble,
            )
        )
    except Exception as e:  # noqa: BLE001
        log.exception("grade_job failed submission=%d", submission_id)
        await send_event(
            GradeEvent(
                submission_id=submission_id,
                event="failed",
                error=f"{type(e).__name__}: {e}",
            )
        )
