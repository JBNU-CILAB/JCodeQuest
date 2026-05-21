from sqlalchemy import func
from sqlmodel import Session, select

from . import vault
from .models import SessionRow, SubmissionRow, TutorMessageRow, UserRow, _utcnow


def get_user(session: Session, user_id: int) -> UserRow | None:
    return session.get(UserRow, user_id)


def get_or_create_user(
    session: Session,
    *,
    provider: str,
    external_id: str,
    display_name: str,
    email: str | None = None,
    avatar_url: str | None = None,
    is_anonymous: bool | None = None,
) -> UserRow:
    """IdP 콜백/스텁이 호출. (provider, external_id)로 멱등.

    avatar_url과 is_anonymous는 *신규 가입 시점에만* IdP가 준 값을 초기값으로 쓴다.
    기존 row에는 덮어쓰지 않는다 — PATCH /me가 단일 source of truth. 그렇지 않으면
    사용자가 업로드한 커스텀 아바타를 매 요청마다 OAuth picture URL로 되돌려놓아
    리더보드에서 새로고침할 때마다 기본 이미지로 떨어진다.
    (캐싱된 stale JWT가 PATCH 직후 새 값을 덮어쓰는 레이스 방지가 핵심.)
    """
    stmt = select(UserRow).where(
        UserRow.provider == provider,
        UserRow.external_id == external_id,
    )
    row = session.exec(stmt).first()
    if row is not None:
        return row

    row = UserRow(
        provider=provider,
        external_id=external_id,
        display_name=display_name,
        email=email,
        avatar_url=avatar_url,
        is_anonymous=bool(is_anonymous) if is_anonymous is not None else False,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


_UNSET: object = object()


def update_user_profile(
    session: Session,
    user_id: int,
    *,
    nickname: str | None | object = _UNSET,
    grade: int | None | object = _UNSET,
    department: str | None | object = _UNSET,
    is_anonymous: bool | object = _UNSET,
    avatar_url: str | None | object = _UNSET,
) -> UserRow | None:
    """학년/학과/닉네임/익명여부/아바타 URL을 부분 갱신. 인자 미전달(_UNSET)이면 그 필드는 안 건드림.
    None을 명시적으로 넘기면 해당 필드를 NULL로 비운다(is_anonymous는 None 비허용).
    avatar_url에 None을 넘기면 리더보드/타인 노출 화면에서 identicon fallback으로 떨어진다."""
    row = session.get(UserRow, user_id)
    if row is None:
        return None

    if nickname is not _UNSET:
        row.nickname = nickname  # type: ignore[assignment]
    if grade is not _UNSET:
        row.grade = grade  # type: ignore[assignment]
    if department is not _UNSET:
        row.department = department  # type: ignore[assignment]
    if is_anonymous is not _UNSET:
        row.is_anonymous = bool(is_anonymous)
    if avatar_url is not _UNSET:
        row.avatar_url = avatar_url  # type: ignore[assignment]

    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_user_api_key(
    session: Session, user_id: int, *, api_key: str | None
) -> UserRow | None:
    """본인 학내 GPT API 키를 Supabase Vault에 저장하고 UserRow엔 UUID만 박는다.
    빈 값으로 호출하면 Vault 행을 지우고 UUID도 비운다."""
    row = session.get(UserRow, user_id)
    if row is None:
        return None

    if not api_key:
        vault.delete_secret(session, row.api_key_secret_id)
        row.api_key_secret_id = None
    else:
        row.api_key_secret_id = vault.store_secret(
            session,
            name=f"jcq_user_{user_id}_api_key",
            value=api_key,
            existing_id=row.api_key_secret_id,
        )
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_user_api_key(session: Session, user_id: int) -> str | None:
    """튜터 호출 시 사용. Vault에서 복호화해서 평문 키를 돌려준다."""
    row = session.get(UserRow, user_id)
    if row is None:
        return None
    return vault.read_secret(session, row.api_key_secret_id)


def list_users_admin(
    session: Session,
    *,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[UserRow, int]]:
    """admin 목록 — (UserRow, submission_count) 튜플. submission_count는 cascade 영향
    크기를 사전 노출하기 위해 같이 계산. search는 display_name/email/nickname의
    부분 일치(LIKE)."""
    stmt = (
        select(UserRow, func.count(SubmissionRow.id))
        .outerjoin(SubmissionRow, SubmissionRow.user_id == UserRow.id)  # type: ignore[arg-type]
        .group_by(UserRow.id)
        .order_by(UserRow.id.desc())  # type: ignore[union-attr]
    )
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            (UserRow.display_name.ilike(like))  # type: ignore[union-attr]
            | (UserRow.email.ilike(like))  # type: ignore[union-attr]
            | (UserRow.nickname.ilike(like))  # type: ignore[union-attr]
        )
    rows = session.exec(stmt.offset(offset).limit(limit)).all()
    return [(u, int(c)) for (u, c) in rows]


def clear_user_api_key(session: Session, user_id: int) -> bool:
    """admin이 사용자 동의 없이 강제로 API 키만 제거. vault 행도 같이 삭제.
    유저는 그대로 보존. 사용자 본인이 다시 등록할 수 있다."""
    row = session.get(UserRow, user_id)
    if row is None:
        return False
    if row.api_key_secret_id is None:
        return True  # already cleared — idempotent
    vault.delete_secret(session, row.api_key_secret_id)
    row.api_key_secret_id = None
    row.updated_at = _utcnow()
    session.add(row)
    session.commit()
    return True


def delete_user(session: Session, user_id: int) -> dict[str, int] | None:
    """유저 + 연관 row 전부 cascade 삭제. 단일 트랜잭션, 마지막에 한 번만 commit.

    delete_problem과 동일한 이유로 SQLAlchemy unit-of-work는 FK 순서를 못 잡으므로
    각 코호트 사이에 `session.flush()`로 SQL 순서를 강제한다.
    순서: tutor_messages → submissions → sessions → vault.secret → user.

    반환: {submissions, tutor_messages, sessions} 카운트. 유저 없으면 None.
    """
    row = session.get(UserRow, user_id)
    if row is None:
        return None
    counts = {"submissions": 0, "tutor_messages": 0, "sessions": 0}

    # 1) 이 유저의 submissions에 묶인 tutor_messages 먼저
    sub_ids = [
        s.id for s in session.exec(
            select(SubmissionRow).where(SubmissionRow.user_id == user_id)
        ).all() if s.id is not None
    ]
    if sub_ids:
        tms = list(
            session.exec(
                select(TutorMessageRow).where(
                    TutorMessageRow.submission_id.in_(sub_ids)  # type: ignore[attr-defined]
                )
            ).all()
        )
        for tm in tms:
            session.delete(tm)
        if tms:
            session.flush()
        counts["tutor_messages"] = len(tms)

    # 2) submissions
    if sub_ids:
        for sid in sub_ids:
            s = session.get(SubmissionRow, sid)
            if s is not None:
                session.delete(s)
        session.flush()
        counts["submissions"] = len(sub_ids)

    # 3) sessions (서버 측 세션 토큰) — 남아 있으면 dangling FK가 된다.
    sess_rows = list(
        session.exec(
            select(SessionRow).where(SessionRow.user_id == user_id)
        ).all()
    )
    for sr in sess_rows:
        session.delete(sr)
    if sess_rows:
        session.flush()
    counts["sessions"] = len(sess_rows)

    # 4) vault secret (API 키)
    if row.api_key_secret_id is not None:
        vault.delete_secret(session, row.api_key_secret_id)
        # delete_secret이 자체 commit을 하므로 row를 다시 가져와야 한다.
        row = session.get(UserRow, user_id)
        assert row is not None

    # 5) user row
    session.delete(row)
    session.commit()
    return counts


def bump_user_exp(session: Session, user_id: int, *, delta: int) -> None:
    """save_grading에서 첫 AC 시점에 호출. 같은 트랜잭션 안에서 commit하기 위해
    세션은 호출자가 관리 — 여기선 add만 하고 flush로 끝낸다."""
    if delta <= 0:
        return
    row = session.get(UserRow, user_id)
    if row is None:
        return
    row.exp += delta
    row.updated_at = _utcnow()
    session.add(row)
    session.flush()
