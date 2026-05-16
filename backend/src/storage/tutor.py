from sqlalchemy import func
from sqlmodel import Session, select

from .models import SubmissionRow, TutorMessageRow


def create_tutor_message(
    session: Session, *, submission_id: int, message: str, is_user_requested: bool = False
) -> TutorMessageRow:
    row = TutorMessageRow(submission_id=submission_id, message=message, is_user_requested=is_user_requested)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def latest_tutor_message(
    session: Session, submission_id: int
) -> TutorMessageRow | None:
    """최신 메시지 1건 — id 내림차순(=created_at 내림차순과 동치, 같은 트랜잭션 내 동시생성도 안전)."""
    stmt = (
        select(TutorMessageRow)
        .where(TutorMessageRow.submission_id == submission_id)
        .order_by(TutorMessageRow.id.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    return session.exec(stmt).first()


def list_tutor_messages(
    session: Session, submission_id: int
) -> list[TutorMessageRow]:
    """오래된 → 최신 순. 시연·감사 시 흐름 따라 읽기 편한 정렬."""
    stmt = (
        select(TutorMessageRow)
        .where(TutorMessageRow.submission_id == submission_id)
        .order_by(TutorMessageRow.id.asc())  # type: ignore[union-attr]
    )
    return list(session.exec(stmt).all())


def count_user_tutor_usage(
    session: Session, *, user_id: int, problem_id: int
) -> int:
    """사용자가 특정 문제에 대해 명시적으로 요청(is_user_requested=True)한 튜터 호출 횟수를 반환."""
    stmt = (
        select(func.count(TutorMessageRow.id))
        .select_from(TutorMessageRow)
        .join(SubmissionRow, TutorMessageRow.submission_id == SubmissionRow.id)
        .where(
            SubmissionRow.user_id == user_id,
            SubmissionRow.problem_id == problem_id,
            TutorMessageRow.is_user_requested == True,
        )
    )
    result = session.exec(stmt).one()
    return result if result is not None else 0
