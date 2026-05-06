import os
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time

from ...schemas import ExecResult, TestCase, TestResult

# 자식 프로세스가 종료 직전 stderr로 흘려보내는 메모리 태그
_PEAK_RE = re.compile(r"\n?__JCQ_PEAK_KB=(\d+)\n?\Z")

# user 코드를 runpy로 __main__에서 실행하고, finally에서 peak RSS를 stderr에 적음.
# SIGKILL로 죽으면 finally가 안 돌아 peak가 0으로 잡힐 수 있음 — TLE/MLE의 기지 사실.
_WRAPPER = (
    "import resource,runpy,sys\n"
    "try:\n"
    "    runpy.run_path(sys.argv[1], run_name='__main__')\n"
    "finally:\n"
    "    ru=resource.getrusage(resource.RUSAGE_SELF)\n"
    "    sys.stderr.write(f'\\n__JCQ_PEAK_KB={ru.ru_maxrss}\\n')\n"
)


def _make_preexec(memory_bytes: int, cpu_seconds: int):
    def fn() -> None:
        # 새 process group으로 분리해서 타임아웃 시 그룹째 SIGKILL 가능
        os.setsid()
        # 메모리(주소 공간) 상한
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        # CPU 시간 — wall-clock 타임아웃과 별도로 폭주 방지
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        # fork 폭탄 방지
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        # 디스크 쓰기 1MB까지
        resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))

    return fn


def run_user_code(
    code: str,
    stdin: str = "",
    *,
    time_limit_ms: int = 2000,
    memory_limit_mb: int = 256,
) -> ExecResult:
    timeout_s = time_limit_ms / 1000.0
    cpu_seconds = max(1, int(timeout_s) + 1)
    memory_bytes = memory_limit_mb * 1024 * 1024

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        code_path = f.name

    start = time.monotonic()
    timed_out = False
    stdout, stderr = "", ""
    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-c", _WRAPPER, code_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            close_fds=True,
            preexec_fn=_make_preexec(memory_bytes, cpu_seconds),
        )
        try:
            stdout, stderr = proc.communicate(stdin, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = proc.communicate(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
    except OSError as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return ExecResult(
            status="RE", stderr=str(e), elapsed_ms=elapsed
        )
    finally:
        try:
            os.unlink(code_path)
        except OSError:
            pass

    elapsed_ms = int((time.monotonic() - start) * 1000)

    peak_kb = 0
    m = _PEAK_RE.search(stderr)
    if m:
        peak_kb = int(m.group(1))
        stderr = _PEAK_RE.sub("", stderr)

    rc = proc.returncode if proc else None
    if timed_out:
        status = "TLE"
    elif rc == 0:
        status = "OK"
    elif "MemoryError" in stderr or rc == -9:
        # SIGKILL이 곧 RLIMIT_AS 초과로 인한 강제 종료일 수 있음
        status = "MLE"
    else:
        status = "RE"

    return ExecResult(
        status=status,
        stdout=stdout,
        stderr=stderr,
        exit_code=rc,
        elapsed_ms=elapsed_ms,
        peak_memory_kb=peak_kb,
    )


def run_all_tests(
    code: str,
    test_cases: list[TestCase],
    *,
    time_limit_ms: int,
    memory_limit_mb: int,
) -> list[TestResult]:
    results: list[TestResult] = []
    for tc in test_cases:
        ex = run_user_code(
            code,
            tc.stdin,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        passed = (
            ex.status == "OK"
            and ex.stdout.rstrip() == tc.expected_stdout.rstrip()
        )
        results.append(
            TestResult(
                ordinal=tc.ordinal,
                passed=passed,
                status=ex.status,
                actual_stdout=ex.stdout if not passed else None,
                error=ex.stderr if ex.status != "OK" else None,
                elapsed_ms=ex.elapsed_ms,
                peak_memory_kb=ex.peak_memory_kb,
            )
        )
    return results
