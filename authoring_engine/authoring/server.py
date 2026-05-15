"""FastAPI 서버 — 출제 파이프라인 + 문제/스팬 조회 API.

DB는 backend가 단일 소유 — 이 서버는 `/internal/*` 라우트로 backend에 위임한다.
sandbox 실행도 마찬가지로 judge_engine의 `/api/sandbox/run`을 호출.

라우터는 `authoring/routers/`에서 정의. /api/health를 제외한 모든 라우트는
`Authorization: Bearer <JCQ_ADMIN_TOKEN>`을 요구한다. 별도 도메인에서 띄우는
대시보드는 `JCQ_DASHBOARD_ORIGIN`(콤마 구분)에 등록해 CORS preflight를 통과시켜야 한다.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, problems, runs, spans, submissions

if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ["LANGSMITH_API_KEY"])
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "jcq-authoring"))


tags_metadata = [
    {"name": "health", "description": "liveness probe (인증 없음)"},
    {"name": "runs", "description": "출제 파이프라인 실행 + SSE 진행 스트림 (admin)"},
    {"name": "problems", "description": "원본/변형 문제 조회·등록·삭제 (admin)"},
    {"name": "submissions", "description": "유저 풀이 기록 조회 (admin)"},
    {"name": "spans", "description": "LangSmith 트레이스 조회 (admin)"},
]


app = FastAPI(
    title="JCodeQuest Authoring Engine",
    description=(
        "LangGraph 파이프라인으로 원본 문제로부터 변형을 생성하는 출제 엔진. "
        "DB·sandbox는 backend·judge_engine에 위임 — 내부 HTTP API로 통신. "
        "/api/health를 제외한 라우트는 Bearer admin 토큰을 요구한다."
    ),
    version="0.3.0",
    openapi_tags=tags_metadata,
)


# CORS — 대시보드 origin은 환경변수로 주입. 미설정이면 동일 origin만 허용.
_origins = [o.strip() for o in os.getenv("JCQ_DASHBOARD_ORIGIN", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app.include_router(health.router)
app.include_router(runs.router)
app.include_router(problems.router)
app.include_router(submissions.router)
app.include_router(spans.router)


@app.on_event("startup")
async def _capture_loop() -> None:
    runs.set_event_loop(asyncio.get_running_loop())
