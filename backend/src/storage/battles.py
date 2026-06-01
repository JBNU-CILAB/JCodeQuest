"""Code Battle(매일 20시 실시간 대전) 저장/집계 계층.

배틀 자체의 상태 머신(scheduled→lobby→active→finished)과 참가자 베스트 결과 캐시,
스코어보드 정렬·순위 보상을 담당한다. 채점은 기존 judge_engine 파이프라인을 그대로
재사용하므로(SubmissionRow.battle_id로만 연결) 여기엔 채점 로직이 없다.

설계 메모:
- 하루 1배틀: BattleRow.battle_date 유니크 제약 + get_or_create의 IntegrityError 흡수로
  스케줄러가 멀티워커/중복 호출돼도 한 판으로 수렴.
- 스코어보드는 participant의 best_* 캐시만 정렬하면 끝 — 매번 제출 전체를 재집계하지 않는다.
  채점이 끝날 때마다 update_participant_from_submission이 '더 좋을 때만' 캐시를 갱신.
- 시각 비교는 leaderboard._iso_week_start와 같은 이유로 aware/naive를 UTC로 수렴시킨다
  (SQLite 라운드트립 후 naive로 돌아옴).
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..schemas import ScoreboardEntry
from .leaderboard import _public_name
from .models import BattleParticipantRow, BattleRow, ProblemRow, SubmissionRow, UserRow
from .users import bump_user_exp

KST = timezone(timedelta(hours=9))

# ── 타이밍 설정 (env로 조정, E2E는 분 단위를 소수로 줄여 초 단위 테스트 가능) ──────────
BATTLE_START_HOUR = int(os.getenv("JCQ_BATTLE_START_HOUR", "20"))   # KST 시작 시각(로비 오픈)
BATTLE_LOBBY_MIN = float(os.getenv("JCQ_BATTLE_LOBBY_MIN", "5"))    # 로비 길이(분)
BATTLE_SOLVE_MIN = float(os.getenv("JCQ_BATTLE_SOLVE_MIN", "20"))   # 풀이 길이(분)

# ── 제출 게이트 (일반 /grade와 독립) ──────────────────────────────────────────────
BATTLE_COOLDOWN_S = float(os.getenv("JCQ_BATTLE_COOLDOWN_S", "10"))
BATTLE_MAX_ATTEMPTS = int(os.getenv("JCQ_BATTLE_MAX_ATTEMPTS", "30"))

# 개발용 상시 개방 모드 — 켜면 시간표를 무시하고 오늘 배틀을 항상 active로 유지한다.
# (프로덕션의 매일 20시 스케줄과 독립. 언제든 참가/제출해 동작을 확인하려는 용도.)
BATTLE_ALWAYS_OPEN = os.getenv("JCQ_BATTLE_ALWAYS_OPEN", "0") == "1"

# ── 순위 보상 (finalize_battle에서 user.exp로 가산) ──────────────────────────────
# 상위 N등 보상(쉼표 구분, 1등부터). 그 외 제출 경험자는 참가 보상.
BATTLE_REWARD_TOP = [
    int(x) for x in os.getenv("JCQ_BATTLE_REWARD_TOP", "50,30,20").split(",") if x.strip()
]
BATTLE_PARTICIPATION_EXP = int(os.getenv("JCQ_BATTLE_PARTICIPATION_EXP", "5"))


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _epoch(dt: datetime | None) -> float:
    """정렬용 타임스탬프. None(미제출)이면 +inf로 맨 뒤."""
    a = _aware(dt)
    return a.timestamp() if a is not None else float("inf")


# ── 타이밍 계산 ────────────────────────────────────────────────────────────────
def battle_window_for(d: date) -> tuple[datetime, datetime, datetime]:
    """주어진 KST 날짜의 (lobby_at, start_at, end_at)를 UTC-aware로 반환.

    lobby_at = 그 날 BATTLE_START_HOUR:00(KST)
    start_at = lobby_at + 로비(분)  (문제 공개)
    end_at   = start_at + 풀이(분)  (순위 확정)
    """
    lobby_kst = datetime(d.year, d.month, d.day, BATTLE_START_HOUR, 0, 0, tzinfo=KST)
    lobby_at = lobby_kst.astimezone(timezone.utc)
    start_at = lobby_at + timedelta(minutes=BATTLE_LOBBY_MIN)
    end_at = start_at + timedelta(minutes=BATTLE_SOLVE_MIN)
    return lobby_at, start_at, end_at


def next_battle_start_at(now: datetime | None = None) -> datetime:
    """다음 배틀의 로비 오픈(시작) 시각 UTC. 진행 중이면 오늘 lobby_at, 끝났으면 내일."""
    now = _aware(now) or datetime.now(timezone.utc)
    d = now.astimezone(KST).date()
    lobby_at, _start, end_at = battle_window_for(d)
    if now < end_at:
        return lobby_at  # 오늘 아직 시작 전이거나 진행 중
    return battle_window_for(d + timedelta(days=1))[0]


def phase_for(battle: BattleRow, now: datetime | None = None) -> str:
    """시각 기준으로 '있어야 할' 단계 계산 — 스케줄러 부팅 보정과 방어적 표시에 사용.
    저장된 status와 별개로 now 기준 단계를 돌려준다(문제 공개 여부는 status를 따른다)."""
    now = _aware(now) or datetime.now(timezone.utc)
    if now < _aware(battle.lobby_at):
        return "scheduled"
    if now < _aware(battle.start_at):
        return "lobby"
    if now < _aware(battle.end_at):
        return "active"
    return "finished"


# ── 배틀 조회/생성/전이 ────────────────────────────────────────────────────────
def get_battle(session: Session, battle_id: int) -> BattleRow | None:
    return session.get(BattleRow, battle_id)


def get_battle_for_date(session: Session, d: date) -> BattleRow | None:
    return session.exec(
        select(BattleRow).where(BattleRow.battle_date == d)
    ).first()


def current_battle(session: Session, *, now: datetime | None = None) -> BattleRow | None:
    """KST '오늘' 날짜의 배틀(없으면 None). 라우터의 GET /battles/current 기반."""
    now = _aware(now) or datetime.now(timezone.utc)
    return get_battle_for_date(session, now.astimezone(KST).date())


def get_or_create_today_battle(
    session: Session, *, now: datetime | None = None
) -> BattleRow:
    """KST '오늘' 배틀을 멱등 생성. 유니크 충돌(동시 호출)이면 기존 row로 수렴."""
    now = _aware(now) or datetime.now(timezone.utc)
    d = now.astimezone(KST).date()
    existing = get_battle_for_date(session, d)
    if existing is not None:
        return existing

    lobby_at, start_at, end_at = battle_window_for(d)
    row = BattleRow(
        battle_date=d,
        status="scheduled",
        lobby_at=lobby_at,
        start_at=start_at,
        end_at=end_at,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        again = get_battle_for_date(session, d)
        assert again is not None
        return again
    session.refresh(row)
    return row


def ensure_always_open(
    session: Session, *, now: datetime | None = None
) -> BattleRow | None:
    """상시 개방 모드 전용 — 오늘 배틀을 항상 active(문제 배정)로 유지.

    멱등: 이미 active + 문제 배정이면 그대로 반환. approved 문제가 하나도 없으면 None.
    active로 처음 전환할 때 start/lobby_at을 now로, end_at을 사실상 무기한으로 세팅해
    solved_seconds 계산(= best_at - start_at)이 음수가 되지 않게 한다.
    """
    now = _aware(now) or datetime.now(timezone.utc)
    battle = get_or_create_today_battle(session, now=now)
    if battle.status == "active" and battle.problem_id is not None:
        return battle

    problem_id = battle.problem_id
    if problem_id is None:
        prob = pick_random_problem(session)
        if prob is None:
            return None
        problem_id = prob.id

    battle.status = "active"
    battle.problem_id = problem_id
    battle.lobby_at = now
    battle.start_at = now
    battle.end_at = now + timedelta(days=3650)  # 사실상 무기한
    session.add(battle)
    session.commit()
    session.refresh(battle)
    return battle


def pick_random_problem(session: Session) -> ProblemRow | None:
    """approved 문제 중 무작위 1개. func.random()은 SQLite·Postgres 공용."""
    return session.exec(
        select(ProblemRow)
        .where(ProblemRow.status == "approved")
        .order_by(func.random())
        .limit(1)
    ).first()


def transition_status(
    session: Session,
    battle_id: int,
    new_status: str,
    *,
    problem_id: int | None = None,
) -> BattleRow | None:
    row = session.get(BattleRow, battle_id)
    if row is None:
        return None
    row.status = new_status
    if problem_id is not None:
        row.problem_id = problem_id
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# ── 참가 ──────────────────────────────────────────────────────────────────────
def get_participant(
    session: Session, battle_id: int, user_id: int
) -> BattleParticipantRow | None:
    return session.exec(
        select(BattleParticipantRow).where(
            BattleParticipantRow.battle_id == battle_id,
            BattleParticipantRow.user_id == user_id,
        )
    ).first()


def count_participants(session: Session, battle_id: int) -> int:
    return int(
        session.exec(
            select(func.count(BattleParticipantRow.id)).where(
                BattleParticipantRow.battle_id == battle_id
            )
        ).one()
    )


def join_battle(
    session: Session, battle_id: int, user_id: int
) -> BattleParticipantRow:
    """멱등 참가 등록. 이미 있으면 그 row 반환."""
    existing = get_participant(session, battle_id, user_id)
    if existing is not None:
        return existing
    row = BattleParticipantRow(battle_id=battle_id, user_id=user_id)
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        again = get_participant(session, battle_id, user_id)
        assert again is not None
        return again
    session.refresh(row)
    return row


# ── 제출 게이트 헬퍼 (배틀 전용 쿨다운/시도 — 일반 /grade와 독립) ──────────────────
def battle_submission_count(session: Session, battle_id: int, user_id: int) -> int:
    return int(
        session.exec(
            select(func.count(SubmissionRow.id)).where(
                SubmissionRow.battle_id == battle_id,
                SubmissionRow.user_id == user_id,
            )
        ).one()
    )


def battle_cooldown_remaining_s(
    session: Session, battle_id: int, user_id: int, *, now: datetime | None = None
) -> float:
    """이 배틀에서 (user)의 마지막 제출 이후 남은 쿨다운 초. 0이면 즉시 제출 가능."""
    if BATTLE_COOLDOWN_S <= 0:
        return 0.0
    last = session.exec(
        select(func.max(SubmissionRow.created_at)).where(
            SubmissionRow.battle_id == battle_id,
            SubmissionRow.user_id == user_id,
        )
    ).one()
    if last is None:
        return 0.0
    now = _aware(now) or datetime.now(timezone.utc)
    elapsed = (now - _aware(last)).total_seconds()
    return max(0.0, BATTLE_COOLDOWN_S - elapsed)


# ── 채점 결과 반영 ──────────────────────────────────────────────────────────────
def update_participant_from_submission(
    session: Session, submission_id: int
) -> int | None:
    """배틀 제출 1건의 채점 결과를 참가자 베스트 캐시에 반영.

    더 좋은 결과(AC 우선 → 통과 테스트 수 → 더 이른 제출 시각)일 때만 best_*를 덮어쓴다.
    반영된 battle_id를 반환(SSE notify 트리거용). 배틀 제출이 아니면 None.
    apply_grading_event의 'done' 분기에서만 호출되므로 제출당 정확히 1회 attempts 증가.
    """
    sub = session.get(SubmissionRow, submission_id)
    if sub is None or sub.battle_id is None:
        return None

    part = get_participant(session, sub.battle_id, sub.user_id)
    if part is None:
        # 정상 흐름에선 submit이 join을 강제하지만, 방어적으로 생성.
        part = BattleParticipantRow(battle_id=sub.battle_id, user_id=sub.user_id)
        session.add(part)

    results = sub.test_results or []
    tests_passed = sum(1 for t in results if t.get("passed"))
    total = len(results)
    is_ac = sub.final_verdict == "AC"
    sub_at = _aware(sub.created_at)

    part.attempts += 1

    no_best_yet = part.best_submission_id is None and part.best_at is None
    take = no_best_yet or _is_better(
        is_ac, tests_passed, sub_at,
        part.is_ac, part.best_tests_passed, _aware(part.best_at),
    )
    if take:
        part.is_ac = is_ac
        part.best_tests_passed = tests_passed
        part.total_tests = total
        part.best_at = sub_at
        part.best_submission_id = submission_id

    session.add(part)
    session.commit()
    return sub.battle_id


def _is_better(
    new_ac: bool, new_passed: int, new_at: datetime | None,
    cur_ac: bool, cur_passed: int, cur_at: datetime | None,
) -> bool:
    """새 결과가 현재 베스트보다 더 좋은가. (AC 우선 → 통과수 → 더 이른 시각)."""
    if new_ac != cur_ac:
        return new_ac
    if new_passed != cur_passed:
        return new_passed > cur_passed
    if cur_at is None:
        return new_at is not None
    if new_at is None:
        return False
    return new_at < cur_at


# ── 스코어보드 ──────────────────────────────────────────────────────────────────
def compute_scoreboard(session: Session, battle_id: int) -> list[ScoreboardEntry]:
    """참가자 베스트 캐시를 정렬해 순위(rank)를 매긴 스코어보드.

    정렬 키 = (AC면 0 / 아니면 1, -통과수, 베스트 시각). AC 그룹이 먼저 오고
    같은 그룹 내에선 통과수 많은 순 → 같은 통과수면 빨리 도달한 순. 미제출자는 맨 뒤.
    """
    battle = session.get(BattleRow, battle_id)
    start_at = _aware(battle.start_at) if battle else None

    rows = session.exec(
        select(
            BattleParticipantRow,
            UserRow.display_name,
            UserRow.is_anonymous,
            UserRow.nickname,
            UserRow.avatar_url,
        ).join(UserRow, UserRow.id == BattleParticipantRow.user_id)  # type: ignore[arg-type]
        .where(BattleParticipantRow.battle_id == battle_id)
    ).all()

    rows_sorted = sorted(
        rows,
        key=lambda it: (
            0 if it[0].is_ac else 1,
            -it[0].best_tests_passed,
            _epoch(it[0].best_at),
        ),
    )

    out: list[ScoreboardEntry] = []
    for idx, (p, name, anon, nick, avatar) in enumerate(rows_sorted, start=1):
        best_at = _aware(p.best_at)
        solved_seconds = (
            (best_at - start_at).total_seconds()
            if best_at is not None and start_at is not None
            else None
        )
        out.append(
            ScoreboardEntry(
                rank=idx,
                user_id=int(p.user_id),
                display_name=_public_name(name, nick, bool(anon)),
                avatar_url=avatar,
                tests_passed=int(p.best_tests_passed),
                total_tests=int(p.total_tests),
                is_ac=bool(p.is_ac),
                attempts=int(p.attempts),
                solved_seconds=solved_seconds,
            )
        )
    return out


# ── 종료/순위 보상 ──────────────────────────────────────────────────────────────
def finalize_battle(session: Session, battle_id: int) -> list[ScoreboardEntry]:
    """스코어보드를 확정해 각 participant.rank를 기록하고 순위 기반 exp를 가산.

    멱등: 이미 rank가 매겨진 배틀이면(재호출) 아무 것도 가산하지 않고 현재 스코어보드만 반환.
    보상: 상위 N등은 BATTLE_REWARD_TOP, 그 외 1회 이상 제출자(attempts>0)는 참가 보상.
    상태(status='finished') 전이는 스케줄러가 담당 — 여기선 순위·보상만.
    """
    parts = session.exec(
        select(BattleParticipantRow).where(
            BattleParticipantRow.battle_id == battle_id
        )
    ).all()

    already = any(p.rank is not None for p in parts)
    board = compute_scoreboard(session, battle_id)
    if already:
        return board  # 중복 가산 방지

    rank_by_user = {e.user_id: e.rank for e in board}
    attempts_by_user = {e.user_id: e.attempts for e in board}

    for p in parts:
        r = rank_by_user.get(p.user_id)
        p.rank = r
        session.add(p)
        if r is None:
            continue
        reward = 0
        if r <= len(BATTLE_REWARD_TOP):
            reward = BATTLE_REWARD_TOP[r - 1]
        elif attempts_by_user.get(p.user_id, 0) > 0:
            reward = BATTLE_PARTICIPATION_EXP
        if reward > 0:
            bump_user_exp(session, p.user_id, delta=reward)

    session.commit()
    return board
