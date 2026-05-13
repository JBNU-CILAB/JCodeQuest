"""채점 엔진 FastAPI 서버 — 큐잉 + webhook 채점 서비스.

엔드포인트:
  POST /api/grade   {submission_id, problem, code} 를 내부 큐에 적재, 즉시 202 반환.
                    워커가 처리 후 backend의 /internal/grade-events 로 결과를 push.
  GET  /api/health  liveness probe

채점 라이프사이클 (backend가 받게 되는 webhook 순서):
  running → done    (테스트/앙상블 정상 완료)
  running → failed  (잡 내부에서 예외 발생)
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# .env가 있으면 로드 — 없으면 OS env에 의존
load_dotenv(Path(__file__).parent.parent / ".env")

# LangSmith — 키가 잡혀 있을 때만 활성. LangChain은 import 시점에 LANGCHAIN_* 를 보므로
# .ensemble import보다 반드시 먼저 설정해야 자동 트레이싱이 켜진다.
if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ["LANGSMITH_API_KEY"])
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "jcq-judge"))

from fastapi import FastAPI, Request, status as http_status
from jcq_shared.schemas import GradeSubmitRequest

from .jobs import grade_job
from .queue import JobQueue

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue = JobQueue(concurrency=int(os.getenv("JCQ_QUEUE_CONCURRENCY", "1")))
    await queue.start()
    app.state.queue = queue
    try:
        yield
    finally:
        await queue.stop()


app = FastAPI(title="JCodeQuest Judge Engine", lifespan=lifespan)


@app.get(
    "/api/health",
    tags=["health"],
    summary="Liveness probe",
)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/grade",
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="채점 작업 큐잉 — 결과는 webhook으로",
    description=(
        "내부 잡 큐에 적재하고 즉시 `202`로 반환한다. 워커가 처리 후 "
        "backend의 `/internal/grade-events` 로 running → done|failed 순서의 "
        "이벤트를 push (Bearer 인증, `JCQ_INTERNAL_SECRET`)."
    ),
)
async def submit(req: GradeSubmitRequest, request: Request) -> dict[str, object]:
    queue: JobQueue = request.app.state.queue
    submission_id = req.submission_id
    problem = req.problem
    code = req.code

    async def _job() -> None:
        await grade_job(submission_id, problem, code)

    await queue.submit(_job)
    return {"status": "queued", "submission_id": submission_id, "pending": queue.pending}
