"""채점 엔진 FastAPI 서버 — 큐잉 + webhook 채점 + 제출 조회 서비스.

엔드포인트:
  POST /api/grade        {submission_id, problem, code} 를 내부 큐에 적재, 즉시 202 반환.
                         워커가 처리 후 backend의 /internal/grade-events 로 결과를 push.
  POST /api/sandbox/run  1회성 동기 sandbox 실행 (authoring_engine의 verify/solver 용).
  GET  /api/submissions  채점 결과 목록 (admin_dashboard 노출 — Bearer admin 토큰 필요).
  GET  /api/submissions/{id}  채점 결과 상세 (코드/votes/test_results 포함).
  GET  /api/stats/verdicts    시계열 판정 카운트 (admin 그래프).
  GET  /api/stats/judges      시계열 모델별 투표 추세 (admin 그래프).
  GET    /api/users               유저 목록 (admin).
  DELETE /api/users/{id}          유저 cascade 삭제 (제출/튜터/세션).
  DELETE /api/users/{id}/api-key  유저 API 키 강제 제거.
  GET  /api/health       liveness probe

채점 라이프사이클 (backend가 받게 되는 webhook 순서):
  running → done    (테스트/앙상블 정상 완료)
  running → failed  (잡 내부에서 예외 발생)
"""
from __future__ import annotations

import asyncio
import hmac
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

from fastapi import FastAPI, Header, HTTPException, Request, status as http_status
from fastapi.middleware.cors import CORSMiddleware
from jcq_shared.schemas import ExecResult, GradeSubmitRequest, SandboxRunRequest

from .jobs import grade_job
from .queue import JobQueue
from .routers import stats as stats_router
from .routers import submissions as submissions_router
from .routers import users as users_router
from .sandbox import run_user_code

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


# CORS — admin_dashboard origin은 환경변수로 주입. 미설정이면 동일 origin만 허용.
_origins = [o.strip() for o in os.getenv("JCQ_DASHBOARD_ORIGIN", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app.include_router(submissions_router.router)
app.include_router(stats_router.router)
app.include_router(users_router.router)


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


def _require_internal_auth(authorization: str | None) -> None:
    """authoring_engine ↔ judge_engine 통신용 — backend와 동일한 시크릿 공유."""
    secret = os.getenv("JCQ_INTERNAL_SECRET", "")
    if not secret:
        raise HTTPException(503, "internal endpoint disabled (JCQ_INTERNAL_SECRET unset)")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(None, 1)[1].strip()
    if not hmac.compare_digest(token, secret):
        raise HTTPException(401, "invalid token")


@app.post(
    "/api/sandbox/run",
    response_model=ExecResult,
    summary="1회성 동기 sandbox 실행 (authoring_engine 전용)",
    description=(
        "큐를 거치지 않고 호출 즉시 코드를 실행하고 ExecResult를 반환한다. "
        "출제 엔진의 verify(reference_code 동작 확인)와 solver(LLM 풀이 채점) 용도. "
        "`Authorization: Bearer <JCQ_INTERNAL_SECRET>` 필요."
    ),
    include_in_schema=False,
)
async def run_sandbox(
    req: SandboxRunRequest,
    authorization: str | None = Header(default=None),
) -> ExecResult:
    _require_internal_auth(authorization)
    # sandbox는 subprocess 기반 동기 — 워커 스레드로 디스패치해 이벤트 루프 미차단
    return await asyncio.to_thread(
        run_user_code,
        req.code,
        req.stdin,
        time_limit_ms=req.time_limit_ms,
        memory_limit_mb=req.memory_limit_mb,
    )
