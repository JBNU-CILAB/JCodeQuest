"""Supabase Vault wrapper — 비밀(여기선 사용자 API 키)을 vault.secrets에 암호화 저장.

운영(Postgres + supabase_vault)에서는:
  - vault.create_secret(secret, name) → UUID 반환, vault.secrets에 pgsodium 암호화 저장
  - vault.update_secret(id, secret, name) → 기존 행 갱신
  - vault.decrypted_secrets 뷰로 복호화 조회

테스트(SQLite)에는 vault 스키마가 없으므로 같은 함수 이름으로 plaintext fallback.
Vault 익스텐션이 없는 경우(개발 환경)엔 Fernet 대칭암호화로 fallback.

호출자는 항상 (secret_id, value) 의미만 다루고, 어떤 백엔드든 동일 인터페이스를 본다.
"""
from __future__ import annotations

import base64
import hashlib
import os
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from cryptography.fernet import Fernet
from .db import engine


def _is_postgres() -> bool:
    return engine.dialect.name.startswith("postgres")


_vault_available: bool | None = None


def _is_vault_available(session: Session) -> bool:
    """Vault 스키마 존재 여부를 1회만 확인(캐싱)."""
    global _vault_available
    if _vault_available is not None:
        return _vault_available
    try:
        session.execute(text("SELECT 1 FROM vault.secrets LIMIT 0"))
        _vault_available = True
    except Exception:
        _vault_available = False
    return _vault_available


def _get_fernet() -> Fernet:
    """JCQ_VAULT_FALLBACK_KEY에서 Fernet 객체 반환.
    없으면 JCQ_INTERNAL_SECRET에서 SHA-256으로 파생."""
    raw = os.getenv("JCQ_VAULT_FALLBACK_KEY")
    if not raw:
        seed = os.getenv("JCQ_INTERNAL_SECRET", "dev-secret-key")
        raw = base64.urlsafe_b64encode(
            hashlib.sha256(seed.encode()).digest()
        ).decode()
    return Fernet(raw.encode())


def store_secret(
    session: Session,
    *,
    name: str,
    value: str,
    existing_id: str | None,
) -> str:
    """비밀을 새로 만들거나 갱신하고 식별자를 돌려준다.

    경로:
    1. SQLite: plaintext 값 그대로 반환
    2. Postgres + Vault: vault UUID 반환
    3. Postgres + 미Vault: Fernet 암호화 + "fernet:..." prefix 반환
    """
    if not _is_postgres():
        # SQLite 테스트 환경
        return value

    # Postgres: Vault 가용성 확인
    if _is_vault_available(session):
        # Vault 사용 가능
        if existing_id and not existing_id.startswith("fernet:"):
            # UUID 갱신 시도
            try:
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
            except (IntegrityError, Exception):
                # update 실패 시 delete → create로 전환 (fallback)
                session.rollback()

        # 새로 생성 시도
        try:
            row = session.execute(
                text("SELECT vault.create_secret(:secret, :name)"),
                {"secret": value, "name": name},
            ).first()
            if row is None or row[0] is None:
                raise RuntimeError("vault.create_secret returned no UUID")
            session.commit()
            return str(row[0])
        except IntegrityError:
            # 이미 같은 이름의 secret이 존재 → delete 후 재생성
            session.rollback()
            try:
                session.execute(
                    text("DELETE FROM vault.secrets WHERE name = :name"),
                    {"name": name},
                )
                session.commit()
                # 다시 create
                row = session.execute(
                    text("SELECT vault.create_secret(:secret, :name)"),
                    {"secret": value, "name": name},
                ).first()
                if row is None or row[0] is None:
                    raise RuntimeError("vault.create_secret returned no UUID after delete+recreate")
                session.commit()
                return str(row[0])
            except Exception as e:
                session.rollback()
                raise e
    else:
        # Vault 미사용 — Fernet fallback
        cipher = _get_fernet()
        encrypted = cipher.encrypt(value.encode()).decode()
        return f"fernet:{encrypted}"


def read_secret(session: Session, secret_id: str | None) -> str | None:
    """식별자로 비밀 복호화. 없으면 None.

    경로:
    1. None 또는 빈 값: None
    2. "fernet:..." prefix: Fernet 복호화
    3. UUID: Vault vault.decrypted_secrets에서 조회
    4. SQLite: 값 그대로 반환
    """
    if secret_id is None:
        return None
    if not secret_id:
        return None

    # Fernet fallback으로 저장된 비밀
    if secret_id.startswith("fernet:"):
        try:
            cipher = _get_fernet()
            encrypted = secret_id[7:]  # "fernet:" 제거
            decrypted = cipher.decrypt(encrypted.encode()).decode()
            return decrypted
        except Exception:
            return None

    if not _is_postgres():
        # SQLite 테스트 fallback: 식별자=값.
        return secret_id

    # Postgres Vault 조회
    row = session.execute(
        text(
            "SELECT decrypted_secret FROM vault.decrypted_secrets "
            "WHERE id = CAST(:id AS uuid)"
        ),
        {"id": secret_id},
    ).first()
    return None if row is None else str(row[0])


def delete_secret(session: Session, secret_id: str | None) -> None:
    """비밀 삭제. Fernet fallback은 no-op (row 자체가 삭제됨)."""
    if secret_id is None:
        return

    # Fernet fallback: no-op (row 삭제 시 자동으로 제거)
    if secret_id.startswith("fernet:"):
        return

    if not _is_postgres():
        return

    # Vault 삭제
    session.execute(
        text("DELETE FROM vault.secrets WHERE id = CAST(:id AS uuid)"),
        {"id": secret_id},
    )
    session.commit()
