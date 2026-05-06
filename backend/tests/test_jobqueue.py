import asyncio

import pytest

from src.judge.jobs import JobQueue


@pytest.mark.asyncio
async def test_queue_runs_jobs():
    q = JobQueue(concurrency=1)
    await q.start()
    seen: list[int] = []

    async def make_job(n: int):
        seen.append(n)

    for i in range(5):
        await q.submit(lambda n=i: make_job(n))
    # 모든 작업이 처리될 때까지 대기 (.task_done은 워커가 호출)
    await q._queue.join()  # type: ignore[attr-defined]
    await q.stop()
    assert sorted(seen) == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_queue_handles_exception_without_stalling():
    q = JobQueue(concurrency=1)
    await q.start()
    counted = 0

    async def boom():
        raise RuntimeError("explode")

    async def add():
        nonlocal counted
        counted += 1

    await q.submit(boom)
    await q.submit(add)
    await q._queue.join()  # type: ignore[attr-defined]
    await q.stop()
    assert counted == 1


@pytest.mark.asyncio
async def test_concurrency_runs_in_parallel():
    q = JobQueue(concurrency=3)
    await q.start()
    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def slow():
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1

    for _ in range(5):
        await q.submit(slow)
    await q._queue.join()  # type: ignore[attr-defined]
    await q.stop()
    assert peak >= 2  # 최소 2개는 동시에 돌았어야 함
