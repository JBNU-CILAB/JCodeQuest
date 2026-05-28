"""사용자 EXP 기반 4단계 티어 (beginner/amateur/professional/master).

핵심 아이디어: 임계값을 절대 EXP가 아니라 **현재 출제된 approved 문제들의 points 합계**
(max_exp)의 %로 잡는다. 새 문제가 승인되어 max_exp가 커지면 임계값도 자동으로 위로
밀려나서 "인플레이션 방지" — 문제 풀이가 누적되어도 master 비율이 안 늘어난다.

- 저장 위치: 캐시는 UserRow.tier 컬럼 그대로 (인덱스 있음, 리더보드 정렬에 쓰임).
- 갱신 시점:
    1) 첫 AC로 exp가 오를 때 (storage/users.py:bump_user_exp 안에서)
    2) approved 문제 집합이나 points가 변할 때 (storage/problems.py 변경 경로들)

임계 % 는 환경변수로 오버라이드:
    JCQ_TIER_AMATEUR_PCT      (default 10)
    JCQ_TIER_PROFESSIONAL_PCT (default 30)
    JCQ_TIER_MASTER_PCT       (default 60)

max_exp == 0(승인 문제 없음)이면 모두 beginner. 정의상 0/0 비율은 0으로 본다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import func
from sqlmodel import Session, select

from .storage.models import ProblemRow, UserRow

# 순서 = 낮은 → 높은. 외부 노출 문자열(소문자) 그대로 UserRow.tier에 저장된다.
TIER_ORDER: tuple[str, ...] = ("beginner", "amateur", "professional", "master")


def _read_pct(env_key: str, default: float) -> float:
    raw = os.getenv(env_key)
    if raw is None or raw.strip() == "":
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    # 0~100 범위로 clamp — 잘못된 값이 들어와도 분포가 깨지지 않게.
    return max(0.0, min(100.0, v))


def _thresholds() -> tuple[float, float, float]:
    """(amateur_pct, professional_pct, master_pct). 0~100 단위.
    오름차순 보장 — 환경변수가 뒤집혀 들어오면 정렬해서 사용한다."""
    a = _read_pct("JCQ_TIER_AMATEUR_PCT", 10.0)
    p = _read_pct("JCQ_TIER_PROFESSIONAL_PCT", 30.0)
    m = _read_pct("JCQ_TIER_MASTER_PCT", 60.0)
    a, p, m = sorted((a, p, m))
    return a, p, m


def get_max_exp(session: Session) -> int:
    """현재 approved 상태인 모든 문제의 points 합계. 한 사용자가 이론상 받을 수 있는
    누적 EXP의 상한(efficiency multiplier=1.0 가정). 승인 문제가 없으면 0."""
    total = session.exec(
        select(func.coalesce(func.sum(ProblemRow.points), 0)).where(
            ProblemRow.status == "approved"
        )
    ).one()
    # SQLAlchemy 2.x: scalar SELECT은 그대로 값을 돌려준다. tuple로 들어오는 경우 대비.
    if isinstance(total, tuple):
        total = total[0]
    return int(total or 0)


def compute_tier(exp: int, max_exp: int) -> str:
    """exp와 max_exp로 티어 문자열을 결정. max_exp==0이면 무조건 beginner."""
    if max_exp <= 0 or exp <= 0:
        return "beginner"
    ratio_pct = (exp / max_exp) * 100.0
    amateur_pct, professional_pct, master_pct = _thresholds()
    if ratio_pct >= master_pct:
        return "master"
    if ratio_pct >= professional_pct:
        return "professional"
    if ratio_pct >= amateur_pct:
        return "amateur"
    return "beginner"


@dataclass(frozen=True)
class TierProgress:
    """프로필/마이페이지에서 진행도 게이지를 그리려고 미리 계산해 둔 묶음.

    - current: 현재 티어
    - next: 다음 티어 (master면 None)
    - exp_to_next: next 진입까지 남은 EXP (master면 0)
    - progress_pct: 현재 티어 구간 내부 진행도 0~100 (master는 100 고정)
    - max_exp: 시스템 전체 가능 EXP (디버깅·표시용)
    """

    current: str
    next: str | None
    exp_to_next: int
    progress_pct: float
    max_exp: int


def tier_progress(exp: int, max_exp: int) -> TierProgress:
    current = compute_tier(exp, max_exp)
    if max_exp <= 0:
        return TierProgress(
            current=current, next="amateur", exp_to_next=0, progress_pct=0.0, max_exp=0
        )

    amateur_pct, professional_pct, master_pct = _thresholds()
    # 티어 시작점들을 절대 EXP로 환산. 0(beginner) + 세 개 컷.
    cuts: list[tuple[str, int]] = [
        ("beginner", 0),
        ("amateur", int(round(max_exp * amateur_pct / 100.0))),
        ("professional", int(round(max_exp * professional_pct / 100.0))),
        ("master", int(round(max_exp * master_pct / 100.0))),
    ]

    idx = TIER_ORDER.index(current)
    band_start = cuts[idx][1]
    if idx + 1 < len(cuts):
        band_end = cuts[idx + 1][1]
        nxt: str | None = cuts[idx + 1][0]
    else:
        # master: 끝이 없으므로 max_exp까지 한 칸으로 본다.
        band_end = max_exp
        nxt = None

    span = max(1, band_end - band_start)
    inner = max(0, min(exp, band_end) - band_start)
    pct = 100.0 if nxt is None else (inner / span) * 100.0
    exp_to_next = 0 if nxt is None else max(0, band_end - exp)
    return TierProgress(
        current=current,
        next=nxt,
        exp_to_next=exp_to_next,
        progress_pct=pct,
        max_exp=max_exp,
    )


def recompute_user_tier(
    session: Session, user_id: int, *, max_exp: int | None = None
) -> str | None:
    """단일 사용자 티어를 다시 계산해서 UserRow.tier에 반영. flush까지만 — commit은 호출자.
    바뀐 게 없으면 DB write를 생략한다. 사용자 없으면 None."""
    row = session.get(UserRow, user_id)
    if row is None:
        return None
    if max_exp is None:
        max_exp = get_max_exp(session)
    new_tier = compute_tier(row.exp, max_exp)
    if row.tier != new_tier:
        row.tier = new_tier
        session.add(row)
        session.flush()
    return new_tier


def recompute_all_tiers(session: Session) -> int:
    """전체 사용자 티어를 max_exp 변동 이후에 갱신. (id, exp, tier) 세트만 가져와서
    바뀐 row만 UPDATE. commit까지 발행. 변경 row 수를 반환한다.

    문제 승인/은퇴/삭제·points 변경처럼 max_exp가 바뀌면 모든 사용자의 비율이 같이
    움직이므로 부분 갱신은 의미 없다 — 한 번에 쓸어준다."""
    max_exp = get_max_exp(session)
    rows: Iterable[UserRow] = session.exec(select(UserRow)).all()
    changed = 0
    for row in rows:
        new_tier = compute_tier(row.exp, max_exp)
        if row.tier != new_tier:
            row.tier = new_tier
            session.add(row)
            changed += 1
    if changed:
        session.flush()
        session.commit()
    return changed
