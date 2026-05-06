from dataclasses import dataclass

from sqlmodel import Session, select

from ..schemas import EnsembleResult
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
    verdicts = session.exec(
        select(SubmissionRow.final_verdict).where(
            SubmissionRow.user_id == user_id,
            SubmissionRow.problem_id == problem_id,
        )
    ).all()
    return AttemptStatus(
        attempts=len(verdicts),
        solved=any(v == "AC" for v in verdicts),
    )


def create_submission(
    session: Session, *, user_id: int, problem_id: int, code: str
) -> int:
    row = SubmissionRow(user_id=user_id, problem_id=problem_id, code=code)
    .session.add(row)
    session.commit()
    session.refresh(row)
    assert row.id is not None
    return row.id


def save_grading(
    session: Session,
    submission_id: int,
    ensemble: EnsembleResult,
    *,
    points_on_ac: int = 0,
) -> None:
    row = session.get(SubmissionRow, submission_id)
    if row is None:
        raise ValueError(f"submission {submission_id} not found")
    row.final_verdict = ensemble.final_verdict
    row.mode = ensemble.mode
    row.votes = [v.model_dump() for v in ensemble.votes]
    row.points_awarded = (
        points_on_ac if ensemble.final_verdict == "AC" else None
    )
    session.add(row)
    session.commit()


def get_submission(session: Session, submission_id: int) -> SubmissionRow | None:
    return session.get(SubmissionRow, submission_id)
