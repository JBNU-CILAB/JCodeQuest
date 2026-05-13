"""단일 프로세스 내부 잡 큐. asyncio.Queue + 워커 코루틴 N개."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

JobFactory = Callable[[], Awaitable[None]]
_SENTINEL: object = object()


class JobQueue:
    """외부 의존(Redis, arq, RabbitMQ) 없는 단일 프로세스 큐. 메모리에만 존재 —
    프로세스가 죽으면 큐의 미처리 작업도 함께 사라진다. (영속 큐로 승격하려면
    이 자리에 SQLite/Redis 어댑터를 끼우면 됨.)
    """

    def __init__(self, *, concurrency: int = 1) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._concurrency = max(1, concurrency)
        self._workers: list[asyncio.Task] = []

    async def start(self) -> None:
        if self._workers:
            return
        for i in range(self._concurrency):
            t = asyncio.create_task(self._worker(i), name=f"jcq-judge-worker-{i}")
            self._workers.append(t)
        log.info("JobQueue started (concurrency=%d)", self._concurrency)

    async def stop(self) -> None:
        for _ in self._workers:
            await self._queue.put(_SENTINEL)
        for t in self._workers:
            await t
        self._workers.clear()
        log.info("JobQueue stopped")

    async def submit(self, job: JobFactory) -> None:
        await self._queue.put(job)

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    async def _worker(self, idx: int) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item is _SENTINEL:
                    return
                try:
                    await item()  # type: ignore[misc]
                except Exception:
                    log.exception("worker %d: job raised", idx)
            finally:
                self._queue.task_done()
