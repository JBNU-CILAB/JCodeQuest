"""제출 상태 변경 알림용 단일 프로세스 in-memory pub/sub.
페이로드 없이 wake-up 신호만 전달 — 구독자가 DB에서 현재 상태를 다시 읽음."""
import asyncio
from collections import defaultdict


class SubmissionEventBroker:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, submission_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[submission_id].add(q)
        return q

    def unsubscribe(self, submission_id: int, q: asyncio.Queue) -> None:
        subs = self._subs.get(submission_id)
        if subs is None:
            return
        subs.discard(q)
        if not subs:
            self._subs.pop(submission_id, None)

    def notify(self, submission_id: int) -> None:
        for q in list(self._subs.get(submission_id, ())):
            q.put_nowait(None)
