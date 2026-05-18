"""리더보드 집계 쿼리.

전체 누적은 UserRow.exp를 그대로 정렬해 돌려준다(save_grading의 첫 AC hook이
이미 효율 multiplier 적용된 points를 누적). 주차 집계는 SubmissionRow.points_awarded를
현재 ISO 주 시작(월요일 00:00 UTC) 이후로 잘라서 user별 합산한다.

주의: SubmissionRow.points_awarded는 final_verdict=='AC'인 모든 제출에 기록된다.
실제 운영 흐름에선 solved=True가 추가 제출을 409로 막아 (user, problem)당 AC가 한 번뿐이므로
중복 가산이 발생하지 않는다 — 직접 save_grading을 호출하는 테스트는 본 함수의 정정 대상이 아님.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import Session, select

from .models import SubmissionRow, UserRow, iso_week_of


def _iso_week_start(now: datetime | None = None) -> datetime:
    """현재(또는 주어진) ISO 주차의 월요일 00:00 UTC를 naive datetime으로 반환.

    SubmissionRow.created_at은 SQLite 라운드트립 후 naive(UTC)로 돌아오므로
    비교 양변을 naive로 맞춰야 인덱스 비교가 일관된다.
    """
    now = now or datetime.now(timezone.utc)
    y, w, _ = now.isocalendar()
    return datetime.fromisocalendar(y, w, 1)  # Monday, naive


def list_leaderboard_all(
    session: Session, *, limit: int
) -> list[tuple[int, str, str, int, str | None]]:
    """누적 EXP 상위 N. (user_id, display_name, tier, exp, avatar_url) 튜플 리스트."""
    stmt = (
        select(
            UserRow.id,
            UserRow.display_name,
            UserRow.tier,
            UserRow.exp,
            UserRow.avatar_url,
        )
        .where(UserRow.exp > 0)
        .order_by(UserRow.exp.desc(), UserRow.id.asc())
        .limit(limit)
    )
    return [
        (int(uid), name, tier, int(exp), avatar)
        for uid, name, tier, exp, avatar in session.exec(stmt).all()
    ]


def list_leaderboard_by_grade(
    session: Session, *, grade: int, limit: int
) -> list[tuple[int, str, str, int, str | None]]:
    """특정 학년(1~4) 한정 누적 EXP 상위 N.

    UserRow.grade가 NULL인 사용자(프로필 미설정)는 제외. exp=0 도 제외.
    반환 형태는 list_leaderboard_all과 동일하게 (user_id, display_name, tier, exp, avatar_url).
    """
    stmt = (
        select(
            UserRow.id,
            UserRow.display_name,
            UserRow.tier,
            UserRow.exp,
            UserRow.avatar_url,
        )
        .where(UserRow.grade == grade, UserRow.exp > 0)
        .order_by(UserRow.exp.desc(), UserRow.id.asc())
        .limit(limit)
    )
    return [
        (int(uid), name, tier, int(exp), avatar)
        for uid, name, tier, exp, avatar in session.exec(stmt).all()
    ]


def list_leaderboard_week(
    session: Session, *, limit: int, now: datetime | None = None
) -> tuple[str, list[tuple[int, str, str, int, str | None]]]:
    """이번 ISO 주차 한정 points_awarded 합산 상위 N.

    반환: (집계 대상 주차 'YYYY-Www', entries) — entries는
    (user_id, display_name, tier, points, avatar_url) 튜플.
    """
    now = now or datetime.now(timezone.utc)
    week_label = iso_week_of(now)
    week_start = _iso_week_start(now)

    points_sum = func.coalesce(func.sum(SubmissionRow.points_awarded), 0).label(
        "points"
    )
    stmt = (
        select(
            UserRow.id,
            UserRow.display_name,
            UserRow.tier,
            points_sum,
            UserRow.avatar_url,
        )
        .join(SubmissionRow, SubmissionRow.user_id == UserRow.id)
        .where(
            SubmissionRow.points_awarded.is_not(None),
            SubmissionRow.points_awarded > 0,
            SubmissionRow.created_at >= week_start,
        )
        .group_by(UserRow.id, UserRow.display_name, UserRow.tier, UserRow.avatar_url)
        .order_by(points_sum.desc(), UserRow.id.asc())
        .limit(limit)
    )
    entries = [
        (int(uid), name, tier, int(pts), avatar)
        for uid, name, tier, pts, avatar in session.exec(stmt).all()
    ]
    return week_label, entries
