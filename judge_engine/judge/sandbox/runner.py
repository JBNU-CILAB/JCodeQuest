import os
import resource
import selectors
import signal
import subprocess
import sys
import tempfile
import time

from jcq_shared.schemas import ExecResult, TestCase, TestResult

# 한 자식이 워커 메모리를 폭파하지 못하도록 cap. 알고리즘 출력은 통상 수 KB 이하라 64KB로 충분.
# 초과 시 그룹째 SIGKILL하고 status=RE로 마킹 (stderr에 __JCQ_OUTPUT_LIMIT_EXCEEDED__ 마커).
_MAX_STDOUT_BYTES = 64 * 1024
_MAX_STDERR_BYTES = 64 * 1024

# 자식에 주입되는 격리 wrapper. 보호 강도:
#  (1) sys.path를 stdlib만 남겨 site-packages·현재 디렉토리 차단
#  (2) 네트워크/프로세스 스폰 모듈을 import 단계에서 차단 (sys.modules 캐시 우회도 막음)
#  (3) os의 system/popen/fork/exec*/spawn* 류를 PermissionError로 무력화
#  (4) peak RSS는 stdout/stderr와 분리된 별도 fd로 부모에 보고 — cap에 영향 안 받게
# 보안 한계: pure-Python 격리라 ctypes는 차단하지만 seccomp/namespace 격리가 아님.
# 본격적 적대적 격리는 unshare/seccomp로 별도 보강 필요.
_WRAPPER = '''\
import os, resource, runpy, sys, sysconfig

# (1) stdlib만 sys.path에 남김
_STD = (sysconfig.get_paths()['stdlib'], sysconfig.get_paths()['platstdlib'])
sys.path[:] = [p for p in sys.path if p and p.startswith(_STD)]

# (2) 네트워크/프로세스 스폰 모듈 import 차단
_BLOCKED = frozenset((
    'socket', '_socket', 'ssl', '_ssl',
    'urllib', 'http', 'ftplib', 'smtplib', 'telnetlib',
    'imaplib', 'poplib', 'nntplib',
    'xmlrpc', 'webbrowser', 'socketserver', 'wsgiref',
    'asyncio',
    'subprocess', 'multiprocessing', 'ctypes',
))

# 이미 캐시된 차단 모듈 제거 — `import` 우회 차단 (sys.modules.pop 후 재import 시도해도 블로커가 잡음)
for _m in list(sys.modules):
    _p = _m.split('.')
    if any('.'.join(_p[:i+1]) in _BLOCKED for i in range(len(_p))):
        sys.modules.pop(_m, None)

class _Blocker:
    def find_spec(self, name, path, target=None):
        _p = name.split('.')
        for i in range(len(_p)):
            if '.'.join(_p[:i+1]) in _BLOCKED:
                raise ImportError("module '" + name + "' is blocked in sandbox")
        return None

sys.meta_path.insert(0, _Blocker())

# (3) os의 프로세스 스폰/실행 함수 무력화. RLIMIT_NPROC=64가 OS 레벨 백스톱.
for _name in ('system', 'popen', 'fork', 'forkpty',
              'execv', 'execve', 'execvp', 'execvpe',
              'execl', 'execle', 'execlp', 'execlpe',
              'spawnv', 'spawnve', 'spawnvp', 'spawnvpe',
              'spawnl', 'spawnle', 'spawnlp', 'spawnlpe',
              'posix_spawn', 'posix_spawnp'):
    if hasattr(os, _name):
        def _denied(*a, _n=_name, **kw):
            raise PermissionError("os." + _n + " is blocked in sandbox")
        setattr(os, _name, _denied)

# (4) peak rss는 부모가 지정한 fd로 — stdout/stderr cap과 분리
_PEAK_FD = int(sys.argv[2])
try:
    runpy.run_path(sys.argv[1], run_name='__main__')
finally:
    try:
        _ru = resource.getrusage(resource.RUSAGE_SELF)
        os.write(_PEAK_FD, str(_ru.ru_maxrss).encode())
    except OSError:
        pass
'''


def _make_preexec(memory_bytes: int, cpu_seconds: int):
    def fn() -> None:
        # 새 process group으로 분리해서 타임아웃 시 그룹째 SIGKILL 가능
        os.setsid()
        # 메모리(주소 공간) 상한
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        # CPU 시간 — wall-clock 타임아웃과 별도로 폭주 방지
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        # fork 폭탄 방지 (os.fork 무력화의 OS 레벨 백스톱)
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        # 디스크 쓰기 1MB까지
        resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))

    return fn


def _drain_pipes_capped(
    proc: subprocess.Popen, deadline: float
) -> tuple[bytearray, bytearray, bool, bool]:
    """proc.stdout/stderr를 비차단으로 흡수. cap 도달 또는 deadline 만료 시 즉시 반환.

    return: (stdout, stderr, timed_out, output_exceeded)
    """
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
    sel.register(proc.stderr, selectors.EVENT_READ, "stderr")

    timed_out = False
    exceeded = False
    try:
        while sel.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            # 0.5s 슬라이스: cap/timeout 반응성 확보 + busy loop 회피
            for key, _ in sel.select(min(remaining, 0.5)):
                try:
                    chunk = os.read(key.fileobj.fileno(), 8192)
                except OSError:
                    sel.unregister(key.fileobj)
                    continue
                if not chunk:
                    sel.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    room = _MAX_STDOUT_BYTES - len(stdout_buf)
                    if len(chunk) >= room:
                        stdout_buf.extend(chunk[:room])
                        exceeded = True
                    else:
                        stdout_buf.extend(chunk)
                else:
                    room = _MAX_STDERR_BYTES - len(stderr_buf)
                    if len(chunk) >= room:
                        stderr_buf.extend(chunk[:room])
                        exceeded = True
                    else:
                        stderr_buf.extend(chunk)
            if exceeded:
                break
    finally:
        sel.close()

    return stdout_buf, stderr_buf, timed_out, exceeded


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

    # peak RSS 보고용 별도 파이프 — stderr cap과 무관하게 보존
    peak_r, peak_w = os.pipe()
    os.set_inheritable(peak_w, True)

    start = time.monotonic()
    timed_out = False
    output_exceeded = False
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    proc: subprocess.Popen | None = None
    try:
        # -I: isolated mode (PYTHON* 환경변수 무시, -s, -E 포함)
        # -S: site 모듈 비활성 → site-packages가 sys.path에 자동 추가되지 않음
        proc = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _WRAPPER, code_path, str(peak_w)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            pass_fds=(peak_w,),
            preexec_fn=_make_preexec(memory_bytes, cpu_seconds),
        )
        # 부모는 더 이상 peak_w 쓰지 않음 — 닫아야 child 종료 후 read가 EOF로 끝남
        os.close(peak_w)
        peak_w = -1

        # stdin 전달 후 닫음. test-case stdin은 통상 <10KB라 파이프 버퍼(64KB)에 즉시 흡수됨.
        try:
            if stdin:
                proc.stdin.write(stdin.encode())
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            # 자식이 import 단계에서 죽으면 stdin이 이미 닫혀있음 — 무시
            pass

        stdout_buf, stderr_buf, timed_out, output_exceeded = _drain_pipes_capped(
            proc, start + timeout_s
        )

        if timed_out or output_exceeded:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
        else:
            proc.wait()
    except OSError as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return ExecResult(status="RE", stderr=str(e), elapsed_ms=elapsed)
    finally:
        try:
            os.unlink(code_path)
        except OSError:
            pass
        if peak_w != -1:
            try:
                os.close(peak_w)
            except OSError:
                pass
        # Popen이 들고 있는 파이프 fd 명시적 정리 (워커가 장기 실행이므로 fd leak 방지)
        if proc is not None:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass

    # peak 읽기 — child가 peak_w를 닫았으므로 EOF까지 즉시 반환
    peak_kb = 0
    try:
        peak_data = os.read(peak_r, 64)
        if peak_data:
            try:
                peak_kb = int(peak_data.decode().strip())
            except (ValueError, UnicodeDecodeError):
                # 사용자 코드가 fd 3에 garbage를 썼을 수 있음 — peak는 포기
                peak_kb = 0
    except OSError:
        pass
    finally:
        try:
            os.close(peak_r)
        except OSError:
            pass

    elapsed_ms = int((time.monotonic() - start) * 1000)
    stdout = stdout_buf.decode("utf-8", errors="replace")
    stderr = stderr_buf.decode("utf-8", errors="replace")

    rc = proc.returncode if proc else None

    if output_exceeded:
        marker = (
            f"\n__JCQ_OUTPUT_LIMIT_EXCEEDED__ "
            f"(stdout>{_MAX_STDOUT_BYTES}B or stderr>{_MAX_STDERR_BYTES}B)"
        )
        if marker not in stderr:
            stderr = stderr + marker
        status = "RE"
    elif timed_out:
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
