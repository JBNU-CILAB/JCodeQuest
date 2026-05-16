import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlmodel import Session, select

from ..schemas import EnsembleResult, TestResult
from .models import SubmissionRow
from .users import bump_user_exp

KST = timezone(timedelta(hours=9))

MAX_ATTEMPTS = 3

# 같은 (user, problem)에 대해 두 제출 사이 최소 간격(초). 기본 10s.
# 빠른 sandbox-fail 정찰을 막기 위함 — sandbox-fail/LLM-judged 가리지 않고 모든 제출에 적용.
SUBMISSION_COOLDOWN_S = float(os.getenv("JCQ_SUBMIT_COOLDOWN_S", "10"))


@dataclass(frozen=True)
class AttemptStatus:
    attempts: int
    solved: bool
    last_submitted_at: datetime | None = None  # sandbox-fail 포함 모든 제출 중 가장 최근

    @property
    def can_submit(self) -> bool:
        return not self.solved and self.attempts < MAX_ATTEMPTS

    @property
    def remaining(self) -> int:
        return max(0, MAX_ATTEMPTS - self.attempts)

    def cooldown_remaining_s(self, now: datetime | None = None) -> float:
        """다음 제출까지 남은 초. 0이면 즉시 제출 가능."""
        if self.last_submitted_at is None or SUBMISSION_COOLDOWN_S <= 0:
            return 0.0
        now = now or datetime.now(timezone.utc)
        last = self.last_submitted_at
        # SQLite는 timezone 정보를 떨굼 — 들어올 때 UTC로 가정.
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (now - last).total_seconds()
        return max(0.0, SUBMISSION_COOLDOWN_S - elapsed)


def attempt_status(
    session: Session, user_id: int, problem_id: int
) -> AttemptStatus:
    # 시도 카운트(MAX_ATTEMPTS gate): LLM judge까지 도달한 제출(mode 채워짐)만.
    # last_submitted_at(쿨다운 gate): sandbox-fail 포함 모든 제출 중 가장 최근.
    rows = session.exec(
        select(
            SubmissionRow.final_verdict,
            SubmissionRow.mode,
            SubmissionRow.created_at,
        ).where(
            SubmissionRow.user_id == user_id,
            SubmissionRow.problem_id == problem_id,
        )
    ).all()
    judged = [v for v, m, _ in rows if m is not None]
    last_at = max((c for _, _, c in rows), default=None)
    return AttemptStatus(
        attempts=len(judged),
        solved=any(v == "AC" for v in judged),
        last_submitted_at=last_at,
    )


def create_submission(
    session: Session, *, user_id: int, problem_id: int, code: str
) -> int:
    row = SubmissionRow(user_id=user_id, problem_id=problem_id, code=code)
    session.add(row)
    session.commit()
    session.refresh(row)
    assert row.id is not None
    return row.id


def set_status(session: Session, submission_id: int, status: str) -> None:
    row = session.get(SubmissionRow, submission_id)
    if row is None:
        return
    row.status = status
    session.add(row)
    session.commit()


def save_grading(
    session: Session,
    submission_id: int,
    *,
    final_verdict: str,
    test_results: list[TestResult],
    ensemble: EnsembleResult | None = None,
    points_awarded: int = 0,
) -> None:
    row = session.get(SubmissionRow, submission_id)
    if row is None:
        raise ValueError(f"submission {submission_id} not found")
    row.status = "done"
    row.final_verdict = final_verdict
    row.mode = ensemble.mode if ensemble else None
    row.votes = [v.model_dump() for v in ensemble.votes] if ensemble else None
    row.test_results = [t.model_dump() for t in test_results]
    row.max_elapsed_ms = max(
        (t.elapsed_ms for t in test_results), default=None
    )
    row.peak_memory_kb = max(
        (t.peak_memory_kb for t in test_results), default=None
    )
    row.points_awarded = points_awarded if final_verdict == "AC" else None
    session.add(row)

    # 첫 AC 시점에만 user.exp 가산. attempt_status가 solved이면 POST를 409로 막지만,
    # 직접 save_grading을 호출하는 경로(테스트 등)에서도 중복 가산되지 않도록 방어.
    if final_verdict == "AC" and points_awarded > 0:
        prior_ac = session.exec(
            select(SubmissionRow.id).where(
                SubmissionRow.user_id == row.user_id,
                SubmissionRow.problem_id == row.problem_id,
                SubmissionRow.final_verdict == "AC",
                SubmissionRow.id != submission_id,
            )
        ).first()
        if prior_ac is None:
            bump_user_exp(session, row.user_id, delta=points_awarded)

    session.commit()


def get_submission(session: Session, submission_id: int) -> SubmissionRow | None:
    return session.get(SubmissionRow, submission_id)


@dataclass(frozen=True)
class StreakStats:
    current_streak: int
    longest_streak: int
    last_solved_date: date | None
    daily_solves: list[tuple[date, int]]  # 오래된 → 최신 순


def compute_user_streak(
    session: Session, user_id: int, *, window_days: int = 365
) -> StreakStats:
    """'새 문제 처음 AC한 날' 기준 연속 일수와 잔디 카운트. 날짜는 KST로 환산.

    window_days: daily_solves에 포함할 최근 일수 (오늘 포함, 과거 방향).
    """
    rows = session.exec(
        select(SubmissionRow.problem_id, func.min(SubmissionRow.created_at))
        .where(
            SubmissionRow.user_id == user_id,
            SubmissionRow.final_verdict == "AC",
        )
        .group_by(SubmissionRow.problem_id)
    ).all()

    def to_kst_date(dt: datetime) -> date:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).date()

    today_kst = datetime.now(KST).date()

    counts: dict[date, int] = {}
    for _, dt in rows:
        if dt is None:
            continue
        d = to_kst_date(dt)
        counts[d] = counts.get(d, 0) + 1

    daily = [
        (today_kst - timedelta(days=i), counts.get(today_kst - timedelta(days=i), 0))
        for i in range(window_days - 1, -1, -1)
    ]

    if not counts:
        return StreakStats(0, 0, None, daily)

    solve_dates = sorted(counts.keys())

    longest = 1
    run = 1
    for i in range(1, len(solve_dates)):
        if (solve_dates[i] - solve_dates[i - 1]).days == 1:
            run += 1
        else:
            run = 1
        if run > longest:
            longest = run

    last_solved = solve_dates[-1]
    gap = (today_kst - last_solved).days

    if gap > 1:
        current = 0
    else:
        current = 1
        for i in range(len(solve_dates) - 2, -1, -1):
            if (solve_dates[i + 1] - solve_dates[i]).days == 1:
                current += 1
            else:
                break

    return StreakStats(current, longest, last_solved, daily)


def list_user_submissions(
    session: Session,
    user_id: int,
    *,
    problem_id: int | None = None,
    verdict: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[SubmissionRow], int]:
    """본인 제출 이력 페이지네이션. 최신순(created_at DESC, id DESC)으로 반환."""
    base = select(SubmissionRow).where(SubmissionRow.user_id == user_id)
    if problem_id is not None:
        base = base.where(SubmissionRow.problem_id == problem_id)
    if verdict is not None:
        base = base.where(SubmissionRow.final_verdict == verdict)

    total = session.exec(
        select(func.count()).select_from(base.subquery())
    ).one()

    page = (
        base.order_by(SubmissionRow.created_at.desc(), SubmissionRow.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = session.exec(page).all()
    return list(rows), int(total)
