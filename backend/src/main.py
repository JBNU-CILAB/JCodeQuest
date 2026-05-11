from pathlib import Path

from dotenv import load_dotenv

# src.storage.db가 모듈 임포트 시점에 JCQ_DB_URL을 읽으므로
# src.* 임포트보다 반드시 먼저 실행되어야 한다.
load_dotenv(Path(__file__).parent.parent / ".env")

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.grading import router as grading_router
from .api.tutor import router as tutor_router
from .events import SubmissionEventBroker
from .judge.jobs import JobQueue
from .storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    queue = JobQueue(
        concurrency=int(os.getenv("JCQ_QUEUE_CONCURRENCY", "1"))
    )
    await queue.start()
    app.state.queue = queue
    app.state.events = SubmissionEventBroker()
    try:
        yield
    finally:
        await queue.stop()


app = FastAPI(title="JCodeQuest Backend", lifespan=lifespan)
app.include_router(grading_router)
app.include_router(tutor_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
