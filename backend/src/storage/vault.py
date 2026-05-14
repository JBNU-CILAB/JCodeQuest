"""Supabase Vault wrapper — 비밀(여기선 사용자 API 키)을 vault.secrets에 암호화 저장.

운영(Postgres + supabase_vault)에서는:
  - vault.create_secret(secret, name) → UUID 반환, vault.secrets에 pgsodium 암호화 저장
  - vault.update_secret(id, secret, name) → 기존 행 갱신
  - vault.decrypted_secrets 뷰로 복호화 조회

테스트(SQLite)에는 vault 스키마가 없으므로 같은 함수 이름으로 plaintext fallback.
호출자는 항상 (secret_id, value) 의미만 다루고, 어떤 백엔드든 동일 인터페이스를 본다.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session

from .db import engine


def _is_postgres() -> bool:
    return engine.dialect.name.startswith("postgres")


def store_secret(
    session: Session,
    *,
    name: str,
    value: str,
    existing_id: str | None,
) -> str:
    """비밀을 새로 만들거나 갱신하고 식별자를 돌려준다.
    Postgres: vault UUID. SQLite: plaintext 값 자체(테스트 fallback).
    """
    if not _is_postgres():
        # 테스트 환경 — DB 격리만 보장하면 충분, plaintext 그대로 저장.
        return value

    if existing_id:
        session.execute(
            text(
                "SELECT vault.update_secret("
                "CAST(:id AS uuid), :secret, :name"
                ")"
            ),
            {"id": existing_id, "secret": value, "name": name},
        )
        session.commit()
        return existing_id

    row = session.execute(
        text("SELECT vault.create_secret(:secret, :name)"),
        {"secret": value, "name": name},
    ).first()
    if row is None or row[0] is None:
        raise RuntimeError("vault.create_secret returned no UUID")
    session.commit()
    return str(row[0])


def read_secret(session: Session, secret_id: str | None) -> str | None:
    """식별자로 비밀 복호화. 없으면 None."""
    if secret_id is None:
        return None
    if not _is_postgres():
        # 테스트 fallback: 식별자=값.
        return secret_id

    row = session.execute(
        text(
            "SELECT decrypted_secret FROM vault.decrypted_secrets "
            "WHERE id = CAST(:id AS uuid)"
        ),
        {"id": secret_id},
    ).first()
    return None if row is None else str(row[0])


def delete_secret(session: Session, secret_id: str | None) -> None:
    if secret_id is None or not _is_postgres():
        return
    session.execute(
        text("DELETE FROM vault.secrets WHERE id = CAST(:id AS uuid)"),
        {"id": secret_id},
    )
    session.commit()
