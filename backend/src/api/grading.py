import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status as http_status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..auth.deps import get_current_user
from ..events import SubmissionEventBroker
from ..judge.jobs import grade_submission
from ..schemas import (
    EnsembleResult,
    GradeAcceptedResponse,
    GradeRequest,
    JudgeVote,
    SubmissionStatusResponse,
    TestResult,
)
from ..storage import get_session
from ..storage.models import UserRow
from ..storage.problems import get_problem
from ..storage import submissions as subs_store
from ..storage.submissions import (
    MAX_ATTEMPTS,
    attempt_status,
    create_submission,
    get_submission,
)

router = APIRouter(prefix="/grade", tags=["grading"])

# SSE 유휴 연결 keep-alive 주기. 너무 짧으면 트래픽 낭비, 너무 길면 프록시가 끊음.
_SSE_KEEPALIVE_S = 15.0


def _build_status_response(
    session: Session, submission_id: int
) -> SubmissionStatusResponse | None:
    sub = get_submission(session, submission_id)
    if sub is None:
        return None

    ensemble = None
    if sub.mode is not None and sub.votes is not None:
        ensemble = EnsembleResult(
            final_verdict=sub.final_verdict,  # type: ignore[arg-type]
            mode=sub.mode,  # type: ignore[arg-type]
            votes=[JudgeVote(**v) for v in sub.votes],
        )

    test_results = (
        [TestResult(**t) for t in sub.test_results]
        if sub.test_results is not None
        else None
    )

    return SubmissionStatusResponse(
        submission_id=submission_id,
        status=sub.status,  # type: ignore[arg-type]
        final_verdict=sub.final_verdict,  # type: ignore[arg-type]
        test_results=test_results,
        ensemble=ensemble,
        points_awarded=sub.points_awarded,
    )


@router.post(
    "",
    status_code=http_status.HTTP_202_ACCEPTED,
    response_model=GradeAcceptedResponse,
)
async def submit_grade(
    req: GradeRequest,
    request: Request,
    user: UserRow = Depends(get_current_user),
) -> GradeAcceptedResponse:
    user_id = user.id
    assert user_id is not None
    with get_session() as session:
        problem = get_problem(session, req.problem_id)
        if problem is None:
            raise HTTPException(404, f"problem {req.problem_id} not found")

        astatus = attempt_status(session, user_id, req.problem_id)
        if astatus.solved:
            raise HTTPException(409, "이미 해결한 문제입니다")
        if astatus.attempts >= MAX_ATTEMPTS:
            raise HTTPException(
                429, f"최대 제출 횟수({MAX_ATTEMPTS}회) 초과"
            )

        cooldown = astatus.cooldown_remaining_s()
        if cooldown > 0:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"제출 간 최소 {subs_store.SUBMISSION_COOLDOWN_S:.0f}초 간격 — "
                    f"{cooldown:.1f}초 후 다시 시도"
                ),
                headers={"Retry-After": str(int(cooldown) + 1)},
            )

        submission_id = create_submission(
            session,
            user_id=user_id,
            problem_id=req.problem_id,
            code=req.code,
        )

    queue = request.app.state.queue
    events: SubmissionEventBroker = request.app.state.events
    code = req.code
    await queue.submit(
        lambda: grade_submission(submission_id, problem, code, events=events)
    )

    return GradeAcceptedResponse(submission_id=submission_id, status="queued")


@router.get("/{submission_id}", response_model=SubmissionStatusResponse)
async def get_grade(submission_id: int) -> SubmissionStatusResponse:
    with get_session() as session:
        resp = _build_status_response(session, submission_id)
        if resp is None:
            raise HTTPException(404, f"submission {submission_id} not found")
        return resp


@router.get("/{submission_id}/events")
async def stream_grade_events(
    submission_id: int, request: Request
) -> StreamingResponse:
    with get_session() as session:
        if get_submission(session, submission_id) is None:
            raise HTTPException(404, f"submission {submission_id} not found")

    broker: SubmissionEventBroker = request.app.state.events
    # 스냅샷 읽기 전에 먼저 구독해서, 그 사이 발행된 이벤트를 놓치지 않게 함.
    queue = broker.subscribe(submission_id)

    async def stream():
        try:
            last_payload: str | None = None

            def current_payload() -> tuple[str, str]:
                with get_session() as s:
                    snap = _build_status_response(s, submission_id)
                # 위에서 존재 검증 후엔 None일 수 없음.
                assert snap is not None
                return snap.status, snap.model_dump_json()

            status, payload = current_payload()
            yield f"data: {payload}\n\n".encode()
            last_payload = payload
            if status in ("done", "failed"):
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield b": keep-alive\n\n"
                    continue

                status, payload = current_payload()
                if payload != last_payload:
                    yield f"data: {payload}\n\n".encode()
                    last_payload = payload
                if status in ("done", "failed"):
                    return
        finally:
            broker.unsubscribe(submission_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
