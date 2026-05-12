from pathlib import Path

from dotenv import load_dotenv

# src.storage.db가 모듈 임포트 시점에 JCQ_DB_URL을 읽으므로
# src.* 임포트보다 반드시 먼저 실행되어야 한다.
load_dotenv(Path(__file__).parent.parent / ".env")

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .api.auth import router as auth_router
from .api.grading import router as grading_router
from .api.leaderboard import router as leaderboard_router
from .api.me import router as me_router
from .api.problems import router as problems_router
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500", "http://127.0.0.1:5500",
        "http://localhost:8001", "http://127.0.0.1:8001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth 핸드셰이크의 state/nonce 저장용 임시 쿠키. 사용자 세션은 SessionRow(DB) 기반의
# jcq_session 쿠키로 별도 발급. SESSION_SECRET_KEY 미설정 시 시작 단계에서 fail-fast.
_session_secret = os.getenv("SESSION_SECRET_KEY")
if not _session_secret:
    raise RuntimeError("SESSION_SECRET_KEY is not set")
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    max_age=300,  # OAuth 왕복은 분 단위면 충분
    same_site="lax",
    https_only=False,  # 개발 편의 — prod 배포 시 reverse proxy 단에서 강제
)

app.include_router(auth_router)
app.include_router(me_router)
app.include_router(grading_router)
app.include_router(tutor_router)
app.include_router(problems_router)
app.include_router(leaderboard_router)


@app.get(
    "/health",
    tags=["health"],
    summary="Liveness probe",
    description="서버가 떠 있고 라우터가 마운트됐는지 확인하는 단순 핑.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
