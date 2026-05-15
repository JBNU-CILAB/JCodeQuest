from pathlib import Path

from dotenv import load_dotenv

# src.storage.db가 모듈 임포트 시점에 JCQ_DB_URL을 읽으므로
# src.* 임포트보다 반드시 먼저 실행되어야 한다.
load_dotenv(Path(__file__).parent.parent / ".env")

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.auth import router as auth_router
from .api.grading import router as grading_router
from .api.internal import router as internal_router
from .api.leaderboard import router as leaderboard_router
from .api.me import router as me_router
from .api.notices import router as notices_router
from .api.problems import router as problems_router
from .api.tutor import router as tutor_router
from .events import SubmissionEventBroker
from .storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.events = SubmissionEventBroker()
    yield


app = FastAPI(title="JCodeQuest Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5500", "http://127.0.0.1:5500",
        "http://localhost:8001", "http://127.0.0.1:8001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(me_router)
app.include_router(grading_router)
app.include_router(tutor_router)
app.include_router(problems_router)
app.include_router(leaderboard_router)
app.include_router(notices_router)
app.include_router(internal_router)


@app.get(
    "/health",
    tags=["health"],
    summary="Liveness probe",
    description="서버가 떠 있고 라우터가 마운트됐는지 확인하는 단순 핑.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
