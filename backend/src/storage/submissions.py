from sqlmodel import Session

from ..schemas import EnsembleResult
from .models import SubmissionRow


def create_submission(
    session: Session, *, user_id: int, problem_id: int, code: str
) -> int:
    row = SubmissionRow(user_id=user_id, problem_id=problem_id, code=code)
    session.add(row)
    session.commit()
    session.refresh(row)
    assert row.id is not None
    return row.id


def save_grading(
    session: Session, submission_id: int, ensemble: EnsembleResult
) -> None:
    row = session.get(SubmissionRow, submission_id)
    if row is None:
        raise ValueError(f"submission {submission_id} not found")
    row.final_verdict = ensemble.final_verdict
    row.mode = ensemble.mode
    row.votes = [v.model_dump() for v in ensemble.votes]
    session.add(row)
    session.commit()


def get_submission(session: Session, submission_id: int) -> SubmissionRow | None:
    return session.get(SubmissionRow, submission_id)
