from dataclasses import dataclass

from sqlmodel import Session, select

from ..schemas import EnsembleResult, TestResult
from .models import SubmissionRow

MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class AttemptStatus:
    attempts: int
    solved: bool

    @property
    def can_submit(self) -> bool:
        return not self.solved and self.attempts < MAX_ATTEMPTS

    @property
    def remaining(self) -> int:
        return max(0, MAX_ATTEMPTS - self.attempts)


def attempt_status(
    session: Session, user_id: int, problem_id: int
) -> AttemptStatus:
    # 시도 카운트는 LLM judge까지 도달한 제출(= mode가 채워진 행)만 집계.
    # 테스트 케이스를 통과 못 해 자동 SUS로 떨어진 제출은 시도로 차감하지 않음.
    rows = session.exec(
        select(SubmissionRow.final_verdict, SubmissionRow.mode).where(
            SubmissionRow.user_id == user_id,
            SubmissionRow.problem_id == problem_id,
        )
    ).all()
    judged = [v for v, m in rows if m is not None]
    return AttemptStatus(
        attempts=len(judged),
        solved=any(v == "AC" for v in judged),
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
    session.commit()


def get_submission(session: Session, submission_id: int) -> SubmissionRow | None:
    return session.get(SubmissionRow, submission_id)
