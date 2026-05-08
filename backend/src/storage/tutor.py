from sqlmodel import Session, select

from .models import TutorMessageRow


def create_tutor_message(
    session: Session, *, submission_id: int, message: str
) -> TutorMessageRow:
    row = TutorMessageRow(submission_id=submission_id, message=message)
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
