"""Code Battle 자동 진행 스케줄러.

FastAPI lifespan에서 asyncio task로 띄운다(외부 cron 불필요). 짧은 주기로 폴링하며
시각 기준으로 '있어야 할' 단계와 저장된 status가 다르면 전이시킨다:

  scheduled → lobby   (lobby_at 도달: 입장 가능, 문제 비공개)
  lobby     → active  (start_at 도달: 무작위 approved 문제 공개 + 20분 타이머)
  active    → finished(end_at 도달: 순위 확정 + 보상)

폴링(reconcile) 방식이라 서버가 중간에 죽었다 떠도 첫 tick이 현재 시각에 맞는 단계로
한 번에 따라잡는다(예: lobby 구간에 죽어 있었다면 scheduled→active로 바로 점프).

⚠️ 멀티워커(uvicorn --workers N)에선 워커마다 이 루프가 돈다. battle_date 유니크 제약이
중복 *생성*은 막지만, notify는 워커별 인메모리 브로커라 SSE 구독자가 워커별로 갈린다.
현재 스택은 단일 프로세스라 무관 — 스케일아웃 시 Redis pub/sub 또는 단일 스케줄러로 전환.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from .events import SubmissionEventBroker
from .storage import battles, get_session

log = logging.getLogger(__name__)

# 폴링 주기(초). 전이는 target 시각으로부터 최대 이 값만큼 늦게 일어난다.
# E2E로 초 단위 윈도우를 쓸 땐 JCQ_BATTLE_POLL_S=1 등으로 줄인다.
POLL_S = float(os.getenv("JCQ_BATTLE_POLL_S", "5"))


def _apply_transition(
    session,
    battle,
    target: str,
    broker: SubmissionEventBroker | None,
) -> None:
    assert battle.id is not None
    if target == "lobby":
        battles.transition_status(session, battle.id, "lobby")

    elif target == "active":
        if battle.problem_id is None:
            prob = battles.pick_random_problem(session)
            if prob is None:
                # approved 문제가 하나도 없음 — active로 못 넘어간다. lobby에 머물고 경고.
                log.warning(
                    "Code Battle %s: approved 문제가 없어 active 전이를 보류합니다.",
                    battle.id,
                )
                return
            battles.transition_status(session, battle.id, "active", problem_id=prob.id)
        else:
            battles.transition_status(session, battle.id, "active")

    elif target == "finished":
        battles.transition_status(session, battle.id, "finished")
        battles.finalize_battle(session, battle.id)

    else:
        return

    if broker is not None:
        broker.notify(battle.id)
    log.info("Code Battle %s → %s", battle.id, target)


def _reconcile_once(broker: SubmissionEventBroker | None, now: datetime) -> None:
    with get_session() as session:
        # 상시 개방 모드: 시간표 무시하고 오늘 배틀을 항상 active로 유지.
        if battles.BATTLE_ALWAYS_OPEN:
            before = battles.current_battle(session, now=now)
            before_state = (before.status, before.problem_id) if before else None
            battle = battles.ensure_always_open(session, now=now)
            if (
                battle is not None
                and broker is not None
                and before_state != (battle.status, battle.problem_id)
            ):
                broker.notify(battle.id)  # type: ignore[arg-type]
            return

        battle = battles.current_battle(session, now=now)
        if battle is None:
            # 오늘 배틀 시간대(lobby_at ≤ now < end_at)에 진입했으면 생성, 아니면 대기.
            d = now.astimezone(battles.KST).date()
            lobby_at, _start, end_at = battles.battle_window_for(d)
            if not (lobby_at <= now < end_at):
                return
            battle = battles.get_or_create_today_battle(session, now=now)

        target = battles.phase_for(battle, now)
        if battle.status != target:
            _apply_transition(session, battle, target, broker)


async def battle_scheduler_loop(app) -> None:
    """lifespan에서 create_task로 띄우는 메인 루프. 취소 시 조용히 종료."""
    broker: SubmissionEventBroker | None = getattr(app.state, "battle_events", None)
    log.info("Code Battle 스케줄러 시작 (poll=%.1fs)", POLL_S)
    try:
        while True:
            try:
                _reconcile_once(broker, datetime.now(timezone.utc))
            except Exception:  # noqa: BLE001 — 한 tick 실패가 루프를 죽이면 안 됨
                log.exception("Code Battle 스케줄러 tick 실패")
            await asyncio.sleep(POLL_S)
    except asyncio.CancelledError:
        log.info("Code Battle 스케줄러 종료")
        raise
