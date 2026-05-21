from pathlib import Path

from dotenv import load_dotenv

# src.storage.db가 모듈 임포트 시점에 JCQ_DB_URL을 읽으므로
# src.* 임포트보다 반드시 먼저 실행되어야 한다.
load_dotenv(Path(__file__).parent.parent / ".env")

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.auth import router as auth_router
from .api.grading import router as grading_router
from .api.internal import router as internal_router
from .api.leaderboard import router as leaderboard_router
from .api.me import router as me_router
from .api.notices import router as notices_router
from .api.problems import router as problems_router
from .api.reports import router as reports_router
from .api.submissions import router as submissions_router
from .api.tutor import router as tutor_router
from .events import SubmissionEventBroker
from .storage import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.events = SubmissionEventBroker()
    yield


app = FastAPI(title="JCodeQuest Backend", lifespan=lifespan)

# CORS — 로컬 개발 origin은 항상 허용, 운영 origin은 JCQ_CORS_ORIGINS(쉼표 구분)로 주입.
# allow_credentials=True 상태에서는 "*" 사용 불가 → 정확한 origin 매칭만 가능.
# IP 기반 외부 접속이라면 JCQ_CORS_ORIGIN_REGEX로 패턴(예: ^https?://10\.0\.\d+\.\d+(:\d+)?$)을 줄 수 있다.
_DEFAULT_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5500", "http://127.0.0.1:5500",
    "http://localhost:8001", "http://127.0.0.1:8001",
]
_extra_origins = [
    o.strip() for o in os.getenv("JCQ_CORS_ORIGINS", "").split(",") if o.strip()
]
_origin_regex = os.getenv("JCQ_CORS_ORIGIN_REGEX") or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_ORIGINS + _extra_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SENSITIVE_FIELDS = frozenset({"api_key", "password", "secret", "token"})
_REDACTED = "[REDACTED]"


def _redact(value: Any) -> Any:
    """422 응답/로그 직렬화 직전, 민감 필드 값만 자리표시자로 치환."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k in _SENSITIVE_FIELDS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


@app.exception_handler(RequestValidationError)
async def _redacted_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # FastAPI 기본 422는 errors()에 ctx.input/input과 exc.body로 원본 페이로드를 그대로
    # 흘려보낸다 — api_key를 포함하면 응답·액세스 로그에 평문이 박힌다. 여기서 자리표시자로 치환.
    errors = []
    for err in exc.errors():
        e = dict(err)
        if "input" in e:
            loc = e.get("loc") or ()
            if loc and loc[-1] in _SENSITIVE_FIELDS:
                e["input"] = _REDACTED
            else:
                e["input"] = _redact(e["input"])
        if "ctx" in e and isinstance(e["ctx"], dict):
            e["ctx"] = _redact(e["ctx"])
        errors.append(e)
    return JSONResponse(status_code=422, content={"detail": errors})


app.include_router(auth_router)
app.include_router(me_router)
app.include_router(grading_router)
app.include_router(tutor_router)
app.include_router(problems_router)
app.include_router(submissions_router)
app.include_router(leaderboard_router)
app.include_router(notices_router)
app.include_router(reports_router)
app.include_router(internal_router)


@app.get(
    "/health",
    tags=["health"],
    summary="Liveness probe",
    description="서버가 떠 있고 라우터가 마운트됐는지 확인하는 단순 핑.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
