"""Code Battle(매일 20시 실시간 대전) 공개 API.

매칭/타이머/스코어보드/실시간 브로드캐스트만 담당하고, 채점은 기존 judge_engine
파이프라인을 그대로 재사용한다(제출에 battle_id만 실어 보냄). 실시간 전송은 grading의
SSE 패턴을 그대로 복제 — wake-up 신호(app.state.battle_events)를 받으면 DB에서 스냅샷을
다시 읽어 푸시한다. EventSource는 인증 헤더를 못 싣기 때문에 SSE 스냅샷은 user-agnostic
(joined/my_rank 비움)이고, 프론트는 scoreboard의 user_id를 자기 id와 매칭해 파생한다.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status as http_status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..auth.deps import get_current_user
from ..events import SubmissionEventBroker
from ..judge.client import submit_to_engine
from ..schemas import (
    BattleJoinResponse,
    BattleStatusResponse,
    BattleSubmitRequest,
    BattleSubmitResponse,
)
from ..storage import battles, get_session
from ..storage.models import BattleRow, UserRow
from ..storage.problems import get_problem
from ..storage.submissions import create_submission, set_status
from .problems import _to_detail

log = logging.getLogger(__name__)

router = APIRouter(prefix="/battles", tags=["battles"])

_SSE_KEEPALIVE_S = 15.0

BattleIdPath = Annotated[int, Path(description="배틀 ID", examples=[1])]


def _build_snapshot(
    session: Session,
    battle: BattleRow,
    *,
    now: datetime,
    viewer_user_id: int | None = None,
) -> BattleStatusResponse:
    """배틀 1판의 현재 스냅샷. viewer_user_id가 주어지면(인증 REST) joined/my_rank를 채운다."""
    assert battle.id is not None
    scoreboard = battles.compute_scoreboard(session, battle.id)

    problem = None
    if battle.status in ("active", "finished") and battle.problem_id is not None:
        p = get_problem(session, battle.problem_id)
        if p is not None:
            problem = _to_detail(p)

    joined = False
    my_rank = None
    if viewer_user_id is not None:
        for e in scoreboard:
            if e.user_id == viewer_user_id:
                my_rank = e.rank
                break
        joined = battles.get_participant(session, battle.id, viewer_user_id) is not None

    next_start = (
        battles.next_battle_start_at(now) if battle.status == "finished" else None
    )

    return BattleStatusResponse(
        battle_id=battle.id,
        battle_date=battle.battle_date.isoformat(),
        status=battle.status,  # type: ignore[arg-type]
        server_time=now,
        lobby_at=battle.lobby_at,
        start_at=battle.start_at,
        end_at=battle.end_at,
        next_start_at=next_start,
        always_open=battles.BATTLE_ALWAYS_OPEN,
        problem=problem,
        joined=joined,
        participant_count=len(scoreboard),
        scoreboard=scoreboard,
        my_rank=my_rank,
    )


@router.get(
    "/current",
    response_model=BattleStatusResponse,
    summary="오늘/다음 Code Battle 현황",
    description=(
        "오늘(KST) 배틀이 있으면 그 스냅샷을, 없으면 status=null + 다음 시작 예정 시각을 반환. "
        "클라이언트는 server_time/start_at/end_at으로 카운트다운을 그린다."
    ),
)
def get_current_battle(
    user: UserRow = Depends(get_current_user),
) -> BattleStatusResponse:
    now = datetime.now(timezone.utc)
    with get_session() as session:
        # 상시 개방 모드: 오늘 배틀을 항상 active로 보장(스케줄러 없이도 즉시 동작).
        if battles.BATTLE_ALWAYS_OPEN:
            battle = battles.ensure_always_open(session, now=now)
            if battle is None:
                # approved 문제가 하나도 없어 배틀을 열 수 없음.
                return BattleStatusResponse(server_time=now, always_open=True)
            return _build_snapshot(session, battle, now=now, viewer_user_id=user.id)

        battle = battles.current_battle(session, now=now)
        if battle is None:
            return BattleStatusResponse(
                server_time=now,
                next_start_at=battles.next_battle_start_at(now),
            )
        return _build_snapshot(session, battle, now=now, viewer_user_id=user.id)


@router.get(
    "/{battle_id}",
    response_model=BattleStatusResponse,
    summary="배틀 스냅샷",
    responses={404: {"description": "배틀 없음"}},
)
def get_battle(
    battle_id: BattleIdPath,
    user: UserRow = Depends(get_current_user),
) -> BattleStatusResponse:
    now = datetime.now(timezone.utc)
    with get_session() as session:
        battle = battles.get_battle(session, battle_id)
        if battle is None:
            raise HTTPException(404, f"battle {battle_id} not found")
        return _build_snapshot(session, battle, now=now, viewer_user_id=user.id)


@router.post(
    "/{battle_id}/join",
    response_model=BattleJoinResponse,
    summary="배틀 참가 (멱등)",
    description="lobby/active 단계에서만 참가 가능. 이미 참가했으면 그대로 성공.",
    responses={
        404: {"description": "배틀 없음"},
        409: {"description": "참가할 수 없는 단계 (이미 종료 등)"},
    },
)
def join_battle(
    battle_id: BattleIdPath,
    request: Request,
    user: UserRow = Depends(get_current_user),
) -> BattleJoinResponse:
    assert user.id is not None
    with get_session() as session:
        battle = battles.get_battle(session, battle_id)
        if battle is None:
            raise HTTPException(404, f"battle {battle_id} not found")
        if battle.status not in ("lobby", "active"):
            raise HTTPException(409, "참가할 수 있는 단계가 아닙니다")
        battles.join_battle(session, battle_id, user.id)
        count = battles.count_participants(session, battle_id)

    broker: SubmissionEventBroker = request.app.state.battle_events
    broker.notify(battle_id)
    return BattleJoinResponse(battle_id=battle_id, joined=True, participant_count=count)


@router.post(
    "/{battle_id}/submit",
    status_code=http_status.HTTP_202_ACCEPTED,
    response_model=BattleSubmitResponse,
    summary="배틀 중 코드 제출",
    description=(
        "active 단계에서만 제출 가능. 미참가자는 자동 참가 처리. 일반 /grade와 독립된 "
        "쿨다운·시도 상한을 쓴다(이미 해결한 문제 409·문제당 3회 제한은 적용하지 않음). "
        "채점 결과는 배틀 SSE로 스코어보드에 반영된다."
    ),
    responses={
        404: {"description": "배틀/문제 없음"},
        409: {"description": "진행 중(active)인 배틀이 아님"},
        429: {"description": "쿨다운 중 또는 최대 제출 횟수 초과"},
        503: {"description": "채점 엔진 응답 없음"},
    },
)
async def submit_battle(
    battle_id: BattleIdPath,
    req: BattleSubmitRequest,
    request: Request,
    user: UserRow = Depends(get_current_user),
) -> BattleSubmitResponse:
    assert user.id is not None
    now = datetime.now(timezone.utc)
    with get_session() as session:
        battle = battles.get_battle(session, battle_id)
        if battle is None:
            raise HTTPException(404, f"battle {battle_id} not found")
        if battle.status != "active":
            raise HTTPException(409, "진행 중인 배틀이 아닙니다")
        if battle.problem_id is None:
            raise HTTPException(409, "아직 문제가 공개되지 않았습니다")

        # 미참가자는 자동 참가 (active 화면에 바로 들어와 제출하는 경우).
        if battles.get_participant(session, battle_id, user.id) is None:
            battles.join_battle(session, battle_id, user.id)

        attempts = battles.battle_submission_count(session, battle_id, user.id)
        if attempts >= battles.BATTLE_MAX_ATTEMPTS:
            raise HTTPException(
                429, f"최대 제출 횟수({battles.BATTLE_MAX_ATTEMPTS}회) 초과"
            )

        cooldown = battles.battle_cooldown_remaining_s(
            session, battle_id, user.id, now=now
        )
        if cooldown > 0:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"제출 간 최소 {battles.BATTLE_COOLDOWN_S:.0f}초 간격 — "
                    f"{cooldown:.1f}초 후 다시 시도"
                ),
                headers={"Retry-After": str(int(cooldown) + 1)},
            )

        problem = get_problem(session, battle.problem_id)
        if problem is None:
            raise HTTPException(404, "배틀 문제를 찾을 수 없습니다")

        submission_id = create_submission(
            session,
            user_id=user.id,
            problem_id=battle.problem_id,
            code=req.code,
            battle_id=battle_id,
        )

    # judge_engine 큐에 적재 — 결과는 /internal/grade-events webhook으로 회신되고
    # apply_grading_event가 배틀 스코어 갱신 + battle_events.notify를 수행한다.
    try:
        await submit_to_engine(submission_id, problem, req.code)
    except httpx.HTTPError as e:
        log.error("judge_engine 큐잉 실패 battle=%d sub=%d err=%s", battle_id, submission_id, e)
        with get_session() as session:
            set_status(session, submission_id, "failed")
        raise HTTPException(503, "채점 엔진이 응답하지 않습니다") from e

    # 자동 참가/제출 사실을 구독자에게 즉시 반영(스코어보드는 채점 done 때 다시 갱신됨).
    broker: SubmissionEventBroker = request.app.state.battle_events
    broker.notify(battle_id)
    return BattleSubmitResponse(submission_id=submission_id, status="queued")


@router.get(
    "/{battle_id}/events",
    summary="배틀 상태 SSE 스트림",
    description=(
        "Server-Sent Events. 구독 즉시 현재 스냅샷을 푸시하고, 단계 전이/제출 채점 완료 등 "
        "상태 변경 시마다 동일 페이로드를 푸시한다. 15초마다 keep-alive. status=finished면 종료. "
        "**인증 헤더를 못 싣으므로 joined/my_rank는 비어 있다 — 프론트가 scoreboard로 파생.**"
    ),
    responses={404: {"description": "배틀 없음"}},
)
async def stream_battle_events(
    battle_id: BattleIdPath, request: Request
) -> StreamingResponse:
    with get_session() as session:
        if battles.get_battle(session, battle_id) is None:
            raise HTTPException(404, f"battle {battle_id} not found")

    broker: SubmissionEventBroker = request.app.state.battle_events
    queue = broker.subscribe(battle_id)

    async def stream():
        try:
            last_payload: str | None = None

            def current_payload() -> tuple[str | None, str]:
                now = datetime.now(timezone.utc)
                with get_session() as s:
                    b = battles.get_battle(s, battle_id)
                    assert b is not None
                    snap = _build_snapshot(s, b, now=now)
                return snap.status, snap.model_dump_json()

            status, payload = current_payload()
            yield f"data: {payload}\n\n".encode()
            last_payload = payload
            if status == "finished":
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
                if status == "finished":
                    return
        finally:
            broker.unsubscribe(battle_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
