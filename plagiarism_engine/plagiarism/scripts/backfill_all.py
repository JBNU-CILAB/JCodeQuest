"""기존 AC 데이터 1회 백필 — 시스템 도입 직후 운영자가 수동 1회 실행.

자동 검사는 새 AC 부터만 적용되므로, 도입 시점에 이미 적재된 AC 들에 대해 한 번 일괄로
표절 검사를 돌려 검토 큐를 채워둔다. 같은 (problem, 두 학생) 쌍의 중복은 직전 도입한
storage 단의 upsert 로 자동 dedup 되므로 반복 실행해도 안전.

사용:
  python -m plagiarism.scripts.backfill_all --all                 # 모든 문제
  python -m plagiarism.scripts.backfill_all --problem-id 12       # 단건
  python -m plagiarism.scripts.backfill_all --all --skip-existing # 이미 pair 있는 문제 건너뜀

진행률은 문제별로 한 줄씩 print — 컨테이너/터미널 로그로 확인. 실패는 다음 문제로 격리
(한 문제의 실패가 전체 백필을 중단하지 않음).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# .env 를 server.py 와 동일 위치에서 로드 — config 모듈이 import 시점에 env 를 읽기 때문.
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from plagiarism import backend_client, config  # noqa: E402
from plagiarism.pipeline import run_plagiarism  # noqa: E402


def _has_existing_pairs(problem_id: int) -> bool:
    try:
        pairs = backend_client.list_pairs({"problem_id": problem_id, "limit": 1})
    except Exception:  # noqa: BLE001 — backend 일시 오류면 skip 안 하고 정상 진행
        return False
    return bool(pairs)


def _backfill_problem(problem_id: int, *, skip_existing: bool) -> tuple[bool, str]:
    """단일 문제 처리. (성공 여부, 메시지) 반환."""
    if skip_existing and _has_existing_pairs(problem_id):
        return True, "skip (pairs already exist)"
    t0 = time.monotonic()
    try:
        result = run_plagiarism(problem_id)  # target_user_id 미지정 → 전체 모드
        dur = (time.monotonic() - t0) * 1000
        return True, (
            f"done in {dur:.0f}ms — submissions={result.get('submissions')} "
            f"flagged={result.get('flagged')} run_id={result.get('run_id', '?')[:8]}"
        )
    except Exception as e:  # noqa: BLE001 — 문제별 격리
        dur = (time.monotonic() - t0) * 1000
        return False, f"failed in {dur:.0f}ms — {type(e).__name__}: {e}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="backfill_all", description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="모든 문제 순차 처리")
    g.add_argument("--problem-id", type=int, help="단일 문제 처리")
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="이미 pair 가 적재된 문제는 건너뜀 (재실행 시 신규 문제만 처리하고 싶을 때)",
    )
    args = p.parse_args(argv)

    if not config.ENABLED:
        print("error: plagiarism engine disabled (JCQ_PLAGIARISM_ENABLED=0)", file=sys.stderr)
        return 2

    if args.problem_id is not None:
        ok, msg = _backfill_problem(args.problem_id, skip_existing=args.skip_existing)
        print(f"[{args.problem_id}] {msg}")
        return 0 if ok else 1

    # --all
    try:
        problems = backend_client.list_problems(originals_only=False)
    except Exception as e:  # noqa: BLE001
        print(f"error: failed to list problems — {e}", file=sys.stderr)
        return 2
    ids = sorted(int(p["id"]) for p in problems if p.get("id") is not None)
    print(f"backfill: {len(ids)} problems, skip_existing={args.skip_existing}")
    ok_count = fail_count = skip_count = 0
    for i, pid in enumerate(ids, 1):
        ok, msg = _backfill_problem(pid, skip_existing=args.skip_existing)
        prefix = f"[{i}/{len(ids)}] problem #{pid}"
        print(f"{prefix}: {msg}")
        if msg.startswith("skip"):
            skip_count += 1
        elif ok:
            ok_count += 1
        else:
            fail_count += 1
    print(f"\nsummary: ok={ok_count} skip={skip_count} fail={fail_count} / total={len(ids)}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
