"""JCodeQuest 통합 검증 스크립트.

authoring_engine, backend FastAPI 서버를 (필요하면) 띄우고 다음을 순차 확인한다.
  1) 환경 변수/DB 경로/패키지 임포트
  2) 두 서버의 /health
  3) 코드 제출 채점 (인증→문제 시드→실패 코드 제출→폴링→done/SUS)
  4) authoring_engine 의 DB 조회 API (/api/problems, /api/problems/{id})
  5) (옵션) LLM 경로: 정답 코드 → 앙상블 AC, /tutor, /api/runs SSE

사용 예:
  python scripts/verify_all.py                     # 서버 자동 기동, sandbox 까지만
  python scripts/verify_all.py --with-llm          # Ollama/OpenAI 사용하는 LLM 경로까지
  python scripts/verify_all.py --external          # 이미 떠 있는 서버에 붙기만
"""
from __future__ import annotations

import argparse
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
AUTHORING_DIR = REPO_ROOT / "authoring_engine"

# 채점 큐 / sandbox / 시드 데이터를 직접 호출하려면 src.* 가 임포트 가능해야 한다.
sys.path.insert(0, str(BACKEND_DIR))


# ── 출력 유틸 ──────────────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty()


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s


def ok(stage: str, msg: str = "") -> None:
    print(f"  [{_c('32', ' OK ')}] {stage}" + (f" — {msg}" if msg else ""))


def skip(stage: str, msg: str = "") -> None:
    print(f"  [{_c('33', 'SKIP')}] {stage}" + (f" — {msg}" if msg else ""))


def fail(stage: str, msg: str = "") -> None:
    print(f"  [{_c('31', 'FAIL')}] {stage}" + (f" — {msg}" if msg else ""))


def section(title: str) -> None:
    print()
    print(_c("1;36", f"── {title} " + "─" * max(0, 60 - len(title))))


# ── 서버 기동/정리 ─────────────────────────────────────────────────────────
def _free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _build_subproc_env(extra: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(extra)
    return env


def _spawn(cmd: list[str], cwd: Path, env: dict[str, str], logfile: Path) -> subprocess.Popen:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    f = logfile.open("wb")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=f,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # SIGINT 으로 자식 그룹 전체에 시그널 전달
    )


@contextmanager
def _managed_servers(
    *,
    backend_port: int,
    authoring_port: int,
    start_backend: bool,
    start_authoring: bool,
    common_env: dict[str, str],
) -> Iterator[tuple[subprocess.Popen | None, subprocess.Popen | None]]:
    backend_proc: subprocess.Popen | None = None
    authoring_proc: subprocess.Popen | None = None
    log_dir = REPO_ROOT / ".verify-logs"
    try:
        if start_backend:
            if not _free_port(backend_port):
                raise RuntimeError(f"backend 포트 {backend_port} 이미 사용중 (--external 로 우회)")
            backend_proc = _spawn(
                [sys.executable, "-m", "uvicorn", "src.main:app",
                 "--host", "127.0.0.1", "--port", str(backend_port)],
                cwd=BACKEND_DIR,
                env=_build_subproc_env(common_env),
                logfile=log_dir / "backend.log",
            )
        if start_authoring:
            if not _free_port(authoring_port):
                raise RuntimeError(f"authoring 포트 {authoring_port} 이미 사용중 (--external 로 우회)")
            authoring_proc = _spawn(
                [sys.executable, "-m", "uvicorn", "authoring.server:app",
                 "--host", "127.0.0.1", "--port", str(authoring_port)],
                cwd=AUTHORING_DIR,
                env=_build_subproc_env(common_env),
                logfile=log_dir / "authoring.log",
            )
        yield backend_proc, authoring_proc
    finally:
        for p, name in ((backend_proc, "backend"), (authoring_proc, "authoring")):
            if p is None:
                continue
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait()
            print(f"  [stop] {name} pid={p.pid} (logs: .verify-logs/{name}.log)")


def _tail(path: Path, n: int = 15) -> str:
    if not path.exists():
        return "(로그 없음)"
    try:
        lines = path.read_text(errors="replace").splitlines()
        return "\n      " + "\n      ".join(lines[-n:])
    except Exception as e:  # noqa: BLE001
        return f"(로그 읽기 실패: {e})"


def _wait_health(
    url: str,
    *,
    proc: subprocess.Popen | None = None,
    log_path: Path | None = None,
    timeout_s: float = 30.0,
) -> tuple[bool, str]:
    import httpx
    deadline = time.monotonic() + timeout_s
    last_err = ""
    while time.monotonic() < deadline:
        # 자식이 이미 죽었다면 health 폴링은 무의미 — 즉시 로그 tail 과 함께 실패 반환.
        if proc is not None and proc.poll() is not None:
            tail = _tail(log_path, 20) if log_path else ""
            return False, f"프로세스 종료 rc={proc.returncode}{tail}"
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return True, r.text[:120]
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(0.5)
    return False, last_err or "timeout"


# ── 시드/제출 헬퍼 (script 프로세스 내에서 src.* 직접 사용) ───────────────
def _seed_or_get_problem(title: str = "검증용-2배") -> int:
    from src.schemas import IntentRubric, Problem, TestCase
    from src.storage import get_session, init_db
    from src.storage.problems import create_problem, list_problems

    init_db()
    with get_session() as s:
        for row in list_problems(s):
            if row.title == title:
                return row.id

        p = Problem(
            id=0,
            title=title,
            statement="정수 n이 입력되면 2*n을 출력하라.",
            category="basic",
            level="bronze",
            points=100,
            time_limit_ms=1000,
            memory_limit_mb=128,
            reference_code="n = int(input())\nprint(n * 2)\n",
            intent_rubric=IntentRubric(
                expected_approach="입력을 정수로 파싱 후 2배",
                expected_complexity="O(1)",
                must_handle=["0", "음수"],
                forbidden_patterns=["하드코딩"],
                key_insight="단순 산술",
                one_line_summary="n*2 출력",
            ),
            test_cases=[
                TestCase(ordinal=1, stdin="3\n", expected_stdout="6", is_sample=True),
                TestCase(ordinal=2, stdin="0\n", expected_stdout="0"),
                TestCase(ordinal=3, stdin="-5\n", expected_stdout="-10"),
            ],
        )
        return create_problem(s, p, status="published")


# 일부러 틀리는 코드 — sandbox 단계에서 실패해 ensemble(LLM) 호출 없이 done/SUS 로 끝난다.
_WRONG_CODE = "n = int(input())\nprint(n + 1)\n"
# 정답 코드 — sandbox 통과 → ensemble(Ollama) 호출
_CORRECT_CODE = "n = int(input())\nprint(n * 2)\n"


def _login(client, email: str = "verify@example.com") -> int:
    r = client.post("/auth/dev-login", params={"email": email, "name": "verify"})
    r.raise_for_status()
    return r.json()["user_id"]


def _submit_and_poll(client, *, problem_id: int, code: str, timeout_s: float) -> dict:
    r = client.post("/grade", json={"problem_id": problem_id, "code": code})
    if r.status_code != 202:
        raise RuntimeError(f"POST /grade {r.status_code}: {r.text}")
    sid = r.json()["submission_id"]
    deadline = time.monotonic() + timeout_s
    body: dict = {}
    while time.monotonic() < deadline:
        r = client.get(f"/grade/{sid}")
        r.raise_for_status()
        body = r.json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.5)
    raise TimeoutError(f"submission {sid} 폴링 타임아웃 (status={body.get('status')})")


# ── 스테이지 ───────────────────────────────────────────────────────────────
def stage_env(db_url: str) -> bool:
    section("1. 환경/패키지")
    py = sys.version.split()[0]
    if sys.version_info < (3, 10):
        fail("python", f"3.10+ 필요 (현재 {py})")
        return False
    ok("python", py)

    if not db_url.startswith("sqlite:///"):
        skip("db-path", f"sqlite 외 URL — {db_url}")
    else:
        path = Path(db_url.removeprefix("sqlite:///"))
        path.parent.mkdir(parents=True, exist_ok=True)
        ok("db-path", str(path))

    failed = False
    # 백엔드 부팅이 의존하는 모듈을 import해 봐서 "uvicorn은 떴는데 lifespan에서 죽음" 같은
    # 원인을 환경 단계에서 미리 잡는다 (Connection refused 디버깅 우회).
    for mod in (
        "httpx", "fastapi", "uvicorn", "sqlmodel", "dotenv",
        "itsdangerous",   # starlette.middleware.sessions
        "authlib",        # google OAuth
        "sse_starlette",  # authoring SSE
    ):
        try:
            __import__(mod)
            ok(f"import {mod}")
        except ImportError as e:
            fail(f"import {mod}", str(e))
            failed = True
    return not failed


def stage_health(
    backend_url: str,
    authoring_url: str,
    *,
    backend_proc: subprocess.Popen | None,
    authoring_proc: subprocess.Popen | None,
) -> bool:
    section("2. 서버 /health")
    log_dir = REPO_ROOT / ".verify-logs"
    rb, msg_b = _wait_health(
        f"{backend_url}/health", proc=backend_proc, log_path=log_dir / "backend.log"
    )
    (ok if rb else fail)("backend /health", msg_b)
    ra, msg_a = _wait_health(
        f"{authoring_url}/api/health",
        proc=authoring_proc,
        log_path=log_dir / "authoring.log",
    )
    (ok if ra else fail)("authoring /api/health", msg_a)
    return rb and ra


def stage_grading_sandbox(backend_url: str) -> tuple[bool, int]:
    section("3. 채점 — sandbox 경로 (실패 코드)")
    import httpx
    try:
        problem_id = _seed_or_get_problem()
        ok("seed-problem", f"problem_id={problem_id}")
    except Exception as e:  # noqa: BLE001
        fail("seed-problem", f"{type(e).__name__}: {e}")
        return False, -1

    with httpx.Client(base_url=backend_url, timeout=10.0) as cx:
        try:
            user_id = _login(cx)
            ok("dev-login", f"user_id={user_id}")
        except Exception as e:  # noqa: BLE001
            fail("dev-login", f"{type(e).__name__}: {e}")
            return False, problem_id

        try:
            body = _submit_and_poll(cx, problem_id=problem_id, code=_WRONG_CODE, timeout_s=30)
        except Exception as e:  # noqa: BLE001
            fail("grade(WRONG)", f"{type(e).__name__}: {e}")
            return False, problem_id

        status = body.get("status")
        verdict = body.get("final_verdict")
        tr = body.get("test_results") or []
        n_fail = sum(1 for t in tr if not t.get("passed"))
        if status == "done" and verdict == "SUS" and n_fail >= 1 and body.get("ensemble") is None:
            ok("grade(WRONG)", f"status={status} verdict={verdict} failed={n_fail}/{len(tr)} ensemble=skipped")
            return True, problem_id
        fail("grade(WRONG)",
             f"기대=status=done,verdict=SUS,ensemble=None / 실제={status}/{verdict}/ensemble={body.get('ensemble') is not None}")
        return False, problem_id


def stage_authoring_api(authoring_url: str, problem_id: int) -> bool:
    section("4. authoring_engine 조회 API")
    import httpx
    with httpx.Client(base_url=authoring_url, timeout=10.0) as cx:
        try:
            r = cx.get("/api/problems")
            r.raise_for_status()
            items = r.json()
            ok("GET /api/problems", f"{len(items)}건")
        except Exception as e:  # noqa: BLE001
            fail("GET /api/problems", f"{type(e).__name__}: {e}")
            return False

        if problem_id <= 0:
            skip("GET /api/problems/{id}", "시드된 problem_id 없음")
            return True
        try:
            r = cx.get(f"/api/problems/{problem_id}")
            r.raise_for_status()
            detail = r.json()
            ok("GET /api/problems/{id}",
               f"id={detail['id']} title={detail['title']} testcases={len(detail['test_cases'])}")
        except Exception as e:  # noqa: BLE001
            fail("GET /api/problems/{id}", f"{type(e).__name__}: {e}")
            return False
    return True


def stage_grading_llm(backend_url: str, problem_id: int) -> bool:
    section("5a. 채점 — LLM 앙상블 경로 (정답 코드)")
    if problem_id <= 0:
        skip("grade(CORRECT)", "시드 실패로 스킵")
        return False
    import httpx
    with httpx.Client(base_url=backend_url, timeout=10.0) as cx:
        try:
            _login(cx, email="verify-llm@example.com")
        except Exception as e:  # noqa: BLE001
            fail("dev-login(llm)", f"{type(e).__name__}: {e}")
            return False
        try:
            body = _submit_and_poll(cx, problem_id=problem_id, code=_CORRECT_CODE, timeout_s=240)
        except Exception as e:  # noqa: BLE001
            fail("grade(CORRECT)", f"{type(e).__name__}: {e}")
            return False
        status, verdict = body.get("status"), body.get("final_verdict")
        ens = body.get("ensemble")
        if status == "done" and verdict == "AC" and ens:
            votes = [f"{v['judge_id']}={v['verdict']}" for v in ens["votes"]]
            ok("grade(CORRECT)", f"verdict=AC mode={ens['mode']} votes=[{', '.join(votes)}] "
                                  f"points={body.get('points_awarded')}")
            sid = body["submission_id"] if "submission_id" in body else body.get("submission_id")
            # /tutor
            section("5b. tutor 메시지")
            try:
                r = cx.post(f"/tutor/{sid}", timeout=180.0)
                r.raise_for_status()
                msg = r.json()["message"]
                ok("POST /tutor", f"{len(msg)}자")
            except Exception as e:  # noqa: BLE001
                fail("POST /tutor", f"{type(e).__name__}: {e}")
                return False
            return True
        fail("grade(CORRECT)",
             f"기대=status=done,verdict=AC / 실제={status}/{verdict} ensemble={bool(ens)}")
        return False


def stage_authoring_run(authoring_url: str, problem_id: int) -> bool:
    section("6. authoring_engine /api/runs (LLM)")
    if problem_id <= 0:
        skip("/api/runs", "시드 실패로 스킵")
        return False
    import httpx
    with httpx.Client(base_url=authoring_url, timeout=10.0) as cx:
        try:
            r = cx.post("/api/runs", json={"problem_id": problem_id, "count": 1})
            r.raise_for_status()
            run_id = r.json()["run_id"]
            ok("POST /api/runs", f"run_id={run_id}")
        except Exception as e:  # noqa: BLE001
            fail("POST /api/runs", f"{type(e).__name__}: {e}")
            return False
        # SSE: 최대 5분 대기. done/error 까지만 살펴 본다.
        try:
            with cx.stream("GET", f"/api/runs/{run_id}/events", timeout=300.0) as s:
                updates = 0
                for line in s.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if '"type": "done"' in payload or '"type":"done"' in payload:
                        ok("SSE done", f"updates={updates}")
                        return True
                    if '"type": "error"' in payload or '"type":"error"' in payload:
                        fail("SSE error", payload[:200])
                        return False
                    updates += 1
        except Exception as e:  # noqa: BLE001
            fail("SSE stream", f"{type(e).__name__}: {e}")
            return False
    fail("SSE done", "스트림 종료 신호 없음")
    return False


# ── 엔트리 ────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="JCodeQuest 통합 검증")
    ap.add_argument("--backend-url", default="http://127.0.0.1:8000")
    ap.add_argument("--authoring-url", default="http://127.0.0.1:8800")
    ap.add_argument("--backend-port", type=int, default=8000)
    ap.add_argument("--authoring-port", type=int, default=8800)
    ap.add_argument("--external", action="store_true",
                    help="서버를 새로 띄우지 않고 이미 떠 있는 인스턴스에 붙는다")
    ap.add_argument("--with-llm", action="store_true",
                    help="Ollama/OpenAI를 호출하는 stage 5/6도 실행 (정답 코드/튜터/runs)")
    ap.add_argument("--keep-logs", action="store_true",
                    help="서버 stdout/stderr 로그를 보존 (기본도 .verify-logs/* 에 남음)")
    ap.add_argument(
        "--use-current-db", action="store_true",
        help="환경변수/.env 의 JCQ_DB_URL 을 그대로 사용 "
             "(기본은 .verify-logs/jcq-verify.db 의 격리된 sqlite)",
    )
    ap.add_argument(
        "--db-url", default=None,
        help="명시적으로 DB URL 지정. 미지정+--use-current-db 미지정 시 격리 sqlite 사용",
    )
    args = ap.parse_args()

    # 검증 DB 결정 — 기본은 사용자 운영 DB(Supabase 등)와 격리된 로컬 sqlite.
    scratch_db = REPO_ROOT / ".verify-logs" / "jcq-verify.db"
    if args.db_url:
        db_url = args.db_url
        db_source = "--db-url"
    elif args.use_current_db:
        db_url = os.getenv("JCQ_DB_URL", "")
        if not db_url or "/absolute/path/to/" in db_url:
            db_url = f"sqlite:///{BACKEND_DIR / 'data' / 'jcq.db'}"
        db_source = "--use-current-db (환경변수/.env)"
    else:
        scratch_db.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{scratch_db}"
        db_source = "격리 sqlite (기본)"
    os.environ["JCQ_DB_URL"] = db_url
    print(f"  [db] {db_source}: {db_url}")

    common_env: dict[str, str] = {
        "JCQ_DB_URL": db_url,
        "SESSION_SECRET_KEY": os.getenv("SESSION_SECRET_KEY", secrets.token_hex(32)),
        "JCQ_AUTH_ALLOW_DEV_STUB": os.getenv("JCQ_AUTH_ALLOW_DEV_STUB", "1"),
        "JCQ_COOKIE_INSECURE": os.getenv("JCQ_COOKIE_INSECURE", "1"),
        "JCQ_SUBMIT_COOLDOWN_S": os.getenv("JCQ_SUBMIT_COOLDOWN_S", "0"),
        "JCQ_QUEUE_CONCURRENCY": os.getenv("JCQ_QUEUE_CONCURRENCY", "1"),
    }
    # 이 프로세스에서도 동일 cooldown=0 / dev-stub을 따라야 시드/제출이 막히지 않음
    os.environ.update(common_env)

    if not stage_env(db_url):
        return 1

    start_backend = not args.external
    start_authoring = not args.external

    section("0. 서버 기동")
    if args.external:
        skip("backend uvicorn", "외부 인스턴스 사용")
        skip("authoring uvicorn", "외부 인스턴스 사용")
    else:
        print(f"  backend  → {args.backend_url}  (port {args.backend_port})")
        print(f"  authoring→ {args.authoring_url} (port {args.authoring_port})")

    failures: list[str] = []
    with _managed_servers(
        backend_port=args.backend_port,
        authoring_port=args.authoring_port,
        start_backend=start_backend,
        start_authoring=start_authoring,
        common_env=common_env,
    ) as (backend_proc, authoring_proc):
        if not stage_health(
            args.backend_url,
            args.authoring_url,
            backend_proc=backend_proc,
            authoring_proc=authoring_proc,
        ):
            failures.append("health")
            print(_c("31", "\n서버가 떠 있지 않습니다. .verify-logs/ 를 확인하세요."))
            return 1

        passed, problem_id = stage_grading_sandbox(args.backend_url)
        if not passed:
            failures.append("grading-sandbox")

        if not stage_authoring_api(args.authoring_url, problem_id):
            failures.append("authoring-api")

        if args.with_llm:
            if not stage_grading_llm(args.backend_url, problem_id):
                failures.append("grading-llm")
            if not stage_authoring_run(args.authoring_url, problem_id):
                failures.append("authoring-run")
        else:
            section("5. LLM 경로 — 스킵")
            skip("grade(CORRECT) / tutor / /api/runs", "--with-llm 미지정")

    section("결과")
    if failures:
        print("  " + _c("31", "FAILED stages: " + ", ".join(failures)))
        return 1
    print("  " + _c("32", "모든 stage 통과"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n사용자 중단")
        sys.exit(130)
