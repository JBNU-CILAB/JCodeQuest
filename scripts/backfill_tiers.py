"""기존 사용자 티어 백필 (4단계 도입 1회 마이그레이션).

티어 도입 이전에 가입한 사용자는 UserRow.tier가 기본값 'bronze'에 묶여 있다. 새 산식
(beginner/amateur/professional/master)에 맞춰 한 번 돌려 줘야 의미 있는 값이 들어간다.

사용법:
    source backend/env.sh
    python scripts/backfill_tiers.py
    python scripts/backfill_tiers.py --dry-run

이후의 갱신은 자동:
  - 첫 AC 시점 → storage/users.py:bump_user_exp가 즉시 재계산
  - 문제 status/points 변경, approved 삭제 → storage/problems.py 훅이 전체 재계산
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

# env.sh가 잡혀 있어야 정상 DB로 붙는다. 미설정이면 명시적으로 죽인다.
if not os.getenv("JCQ_DB_URL"):
    sys.stderr.write(
        "JCQ_DB_URL 미설정. `source backend/env.sh` 후 다시 실행해 주세요.\n"
    )
    sys.exit(2)

from sqlmodel import select  # noqa: E402

from src.storage import get_session  # noqa: E402
from src.storage.models import UserRow  # noqa: E402
from src.tier import compute_tier, get_max_exp  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="사용자 티어 일괄 재계산")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB write 없이 변경 예정 사용자 수만 출력",
    )
    args = parser.parse_args()

    with get_session() as session:
        max_exp = get_max_exp(session)
        users = list(session.exec(select(UserRow)).all())
        changes: list[tuple[int, str, str, int]] = []
        for u in users:
            new_tier = compute_tier(u.exp, max_exp)
            if u.tier != new_tier:
                changes.append((u.id or 0, u.tier, new_tier, u.exp))

        print(f"approved 문제 합 max_exp = {max_exp}")
        print(f"전체 사용자 {len(users)}명 중 변경 대상 {len(changes)}명")
        for uid, old, new, exp in changes:
            print(f"  #{uid}: {old} -> {new} (exp={exp})")

        if args.dry_run or not changes:
            return 0

        for uid, _old, new, _exp in changes:
            row = session.get(UserRow, uid)
            if row is not None:
                row.tier = new
                session.add(row)
        session.commit()
        print(f"커밋 완료 — {len(changes)}명 갱신")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
