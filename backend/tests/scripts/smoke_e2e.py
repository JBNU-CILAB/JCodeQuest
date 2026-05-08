"""실제 떠 있는 FastAPI에 붙어 grade → 폴링 → tutor 까지 돌리는 스모크.

전제 (호출자 책임):
- uvicorn이 127.0.0.1:8000에서 떠 있음
- env.sh가 source된 셸에서 실행 — Ollama/OpenAI/JCQ_DB_URL 등은 OS 환경변수에서 읽음.
  서버와 스크립트가 **같은 셸에서 source된 env.sh**를 가져야 DB 위치가 맞음.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# backend/ (이 파일의 두 단계 위)를 sys.path에 넣어야 src.* import 가능 — PYTHONPATH 의존 제거.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import httpx

from src.schemas import IntentRubric, Problem, TestCase
from src.storage import get_session, init_db
from src.storage.problems import create_problem, list_problems

BASE = os.getenv("JCQ_BASE_URL", "http://127.0.0.1:8000")
USER_ID = 99


def seed_problem() -> int:
    init_db()
    with get_session() as session:
        existing = [p for p in list_problems(session) if p.title == "팩토리얼"]
        if existing:
            print(f"[seed] 이미 존재: id={existing[0].id}")
            return existing[0].id

        problem = Problem(
            id=0,
            title="팩토리얼",
            statement="정수 n (0 ≤ n ≤ 12)이 입력되면 n!을 출력하라.",
            category="basic",
            level="bronze",
            points=100,
            time_limit_ms=1000,
            memory_limit_mb=128,
            reference_code=(
                "n = int(input())\n"
                "r = 1\n"
                "for i in range(1, n + 1):\n"
                "    r *= i\n"
                "print(r)\n"
            ),
            intent_rubric=IntentRubric(
                expected_approach="1부터 n까지 누적 곱 (또는 재귀)",
                expected_complexity="O(n)",
                must_handle=["0! = 1", "1! = 1", "12! = 479001600"],
                forbidden_patterns=[
                    "하드코딩된 if/elif 분기로 특정 입력값에 정답 매핑",
                ],
                key_insight="0! = 1, n! = n * (n-1)!",
                one_line_summary="팩토리얼 계산",
            ),
            test_cases=[
                TestCase(ordinal=1, stdin="0\n", expected_stdout="1", is_sample=True),
                TestCase(ordinal=2, stdin="1\n", expected_stdout="1"),
                TestCase(ordinal=3, stdin="5\n", expected_stdout="120"),
                TestCase(ordinal=4, stdin="12\n", expected_stdout="479001600"),
            ],
        )
        pid = create_problem(session, problem, status="published")
        print(f"[seed] 새로 생성: id={pid}")
        return pid


def main() -> int:
    pid = seed_problem()

    code = (
        "n = int(input())\n"
        "r = 1\n"
        "for i in range(1, n + 1):\n"
        "    r *= i\n"
        "print(r)\n"
    )

    with httpx.Client(base_url=BASE, timeout=10.0) as cx:
        print(f"\n[grade] POST /grade (user={USER_ID}, problem={pid})")
        r = cx.post(
            "/grade",
            json={"user_id": USER_ID, "problem_id": pid, "code": code},
        )
        if r.status_code != 202:
            print(f"  -> FAIL {r.status_code}: {r.text}")
            return 1
        accepted = r.json()
        sid = accepted["submission_id"]
        print(f"  -> accepted submission_id={sid}, status={accepted['status']}")

        print("\n[poll] GET /grade/{id} until done…")
        deadline = time.monotonic() + 180  # ensemble 3-judge라 길게
        last_status = None
        while time.monotonic() < deadline:
            r = cx.get(f"/grade/{sid}")
            r.raise_for_status()
            body = r.json()
            if body["status"] != last_status:
                print(f"  status={body['status']}")
                last_status = body["status"]
            if body["status"] in ("done", "failed"):
                break
            time.sleep(1.0)
        else:
            print("  -> TIMEOUT")
            return 1

        print(f"\n[result] final_verdict={body.get('final_verdict')} "
              f"points={body.get('points_awarded')}")
        for t in body.get("test_results") or []:
            mark = "ok" if t["passed"] else "fail"
            print(f"  #{t['ordinal']} {t['status']} [{mark}] "
                  f"{t['elapsed_ms']}ms / {t['peak_memory_kb']}KB")
        ens = body.get("ensemble")
        if ens:
            print(f"  ensemble={ens['final_verdict']} ({ens['mode']})")
            for v in ens["votes"]:
                print(f"    - {v['judge_id']}: {v['verdict']} "
                      f"(intent_match={v['intent_match']}, conf={v['confidence']})")
                print(f"      > {v['rationale'][:160]}")

        if body["status"] != "done":
            print("[tutor] skipped (not done)")
            return 0

        print("\n[tutor] POST /tutor/{id}")
        r = cx.post(f"/tutor/{sid}", timeout=120.0)
        if r.status_code != 200:
            print(f"  -> FAIL {r.status_code}: {r.text}")
            return 1
        msg = r.json()["message"]
        print(f"  message ({len(msg)}자):")
        print("  " + msg.replace("\n", "\n  "))

    return 0


if __name__ == "__main__":
    sys.exit(main())