from src.judge.sandbox import run_user_code, run_all_tests
from src.schemas import TestCase


def test_ok_path():
    r = run_user_code("print('hello')\n", time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "OK"
    assert r.stdout.strip() == "hello"
    assert r.exit_code == 0
    assert r.elapsed_ms >= 0
    # peak memory 태그 회수가 stderr에서 제거됐어야 함
    assert "__JCQ_PEAK_KB" not in r.stderr


def test_stdin_passthrough():
    r = run_user_code(
        "import sys; print(int(sys.stdin.readline()) * 2)",
        stdin="21\n",
        time_limit_ms=2000,
        memory_limit_mb=128,
    )
    assert r.status == "OK"
    assert r.stdout.strip() == "42"


def test_runtime_error():
    r = run_user_code("1/0\n", time_limit_ms=1000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "ZeroDivisionError" in r.stderr


def test_tle_killed():
    r = run_user_code("while True:\n    pass\n", time_limit_ms=300, memory_limit_mb=128)
    assert r.status == "TLE"
    assert r.elapsed_ms >= 300


def test_peak_memory_recorded():
    r = run_user_code(
        "x = bytearray(20 * 1024 * 1024)  # 20MB\nprint('done')",
        time_limit_ms=3000,
        memory_limit_mb=128,
    )
    assert r.status == "OK"
    # 자식 프로세스 자체 RSS도 잡혀서 최소 수MB 이상은 찍혀야 함
    assert r.peak_memory_kb > 1024


def test_run_all_tests_pass():
    code = "n = int(input())\nprint(n * 2)\n"
    cases = [
        TestCase(ordinal=1, stdin="3\n", expected_stdout="6"),
        TestCase(ordinal=2, stdin="-5\n", expected_stdout="-10"),
    ]
    results = run_all_tests(code, cases, time_limit_ms=2000, memory_limit_mb=128)
    assert len(results) == 2
    assert all(r.passed for r in results)


def test_run_all_tests_fail_on_wrong_output():
    code = "n = int(input())\nprint(n + 1)\n"  # 오답
    cases = [TestCase(ordinal=1, stdin="3\n", expected_stdout="6")]
    results = run_all_tests(code, cases, time_limit_ms=2000, memory_limit_mb=128)
    assert results[0].passed is False
    assert results[0].status == "OK"
    assert results[0].actual_stdout is not None


# ───────────────────── 보안: 네트워크/외부 모듈 차단 ─────────────────────


def test_blocks_socket_import():
    code = "import socket\nprint('reached')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "reached" not in r.stdout
    assert "blocked in sandbox" in r.stderr


def test_blocks_low_level_socket():
    code = "import _socket\nprint('reached')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "blocked in sandbox" in r.stderr


def test_blocks_urllib_request():
    code = "from urllib.request import urlopen\nprint('reached')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "blocked in sandbox" in r.stderr


def test_blocks_http_client():
    code = "import http.client\nprint('reached')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"


def test_blocks_ssl():
    code = "import ssl\nprint('reached')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"


def test_blocks_subprocess():
    code = "import subprocess\nprint('reached')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "blocked in sandbox" in r.stderr


def test_blocks_multiprocessing():
    code = "import multiprocessing\nprint('reached')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"


def test_blocks_ctypes():
    # ctypes를 통해 libc.system을 호출하려는 시도 — import 자체에서 막혀야 함
    code = "import ctypes\nctypes.CDLL('libc.so.6').system(b'echo pwned')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "pwned" not in r.stdout


def test_blocks_asyncio():
    code = "import asyncio\nprint('reached')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"


def test_blocks_os_system():
    code = "import os\nos.system('echo pwned')\nprint('after')\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "pwned" not in r.stdout
    assert "os.system is blocked" in r.stderr


def test_blocks_os_fork():
    code = "import os\nos.fork()\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "os.fork is blocked" in r.stderr


def test_blocks_os_execv():
    code = "import os\nos.execv('/bin/sh', ['sh', '-c', 'echo pwned'])\n"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "RE"
    assert "pwned" not in r.stdout
    assert "os.execv is blocked" in r.stderr


def test_socket_blocked_after_sys_modules_purge():
    """sys.modules에서 캐시를 지우고 다시 import해도 블로커가 잡아야 함."""
    code = (
        "import sys\n"
        "sys.modules.pop('socket', None)\n"
        "sys.modules.pop('_socket', None)\n"
        "try:\n"
        "    import socket\n"
        "    print('LEAK')\n"
        "except ImportError:\n"
        "    print('blocked')\n"
    )
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "OK"
    assert "blocked" in r.stdout
    assert "LEAK" not in r.stdout


def test_socket_blocked_after_sys_path_manipulation():
    """sys.path를 강제로 재설정해도 socket 류는 import 단계에서 거부."""
    code = (
        "import sys\n"
        "sys.path = ['/usr/lib/python3', '/usr/lib/python3.14',\n"
        "            '/usr/lib/python3.14/lib-dynload',\n"
        "            '/usr/lib/python3.14/site-packages'] + sys.path\n"
        "try:\n"
        "    import socket\n"
        "    print('LEAK')\n"
        "except ImportError:\n"
        "    print('blocked')\n"
    )
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "OK"
    assert "blocked" in r.stdout
    assert "LEAK" not in r.stdout


def test_no_site_packages_in_sys_path():
    """워커 venv의 site-packages가 자식 sys.path에 절대 끼지 않아야 함."""
    code = (
        "import sys\n"
        "leak = [p for p in sys.path if 'site-packages' in p or 'dist-packages' in p]\n"
        "print('LEAK' if leak else 'clean')\n"
    )
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "OK"
    assert r.stdout.strip() == "clean"


def test_allowed_stdlib_modules_still_work():
    """일반 알고리즘 stdlib는 영향 없어야 함."""
    code = (
        "import math, collections, itertools, heapq, bisect, functools\n"
        "from collections import deque, Counter\n"
        "print(math.gcd(12, 18), len(Counter('aab')))\n"
    )
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "OK"
    assert r.stdout.strip() == "6 2"


# ───────────────────── 보안: stdout/stderr cap ─────────────────────


def test_stdout_cap_kills_process():
    """1MB stdout 시도 → cap에서 잘리고 SIGKILL → RE + 마커."""
    code = (
        "import sys\n"
        "for _ in range(200):\n"
        "    sys.stdout.write('A' * 10000)\n"
        "    sys.stdout.flush()\n"
        "print('UNREACHED')\n"
    )
    r = run_user_code(code, time_limit_ms=5000, memory_limit_mb=256)
    assert r.status == "RE"
    # cap 만큼만 보존 — read chunk(8KB) 단위 슬랙 허용
    assert len(r.stdout) <= 64 * 1024 + 8192
    assert "UNREACHED" not in r.stdout
    assert "__JCQ_OUTPUT_LIMIT_EXCEEDED__" in r.stderr


def test_stderr_cap_kills_process():
    code = (
        "import sys\n"
        "for _ in range(200):\n"
        "    sys.stderr.write('E' * 10000)\n"
        "    sys.stderr.flush()\n"
    )
    r = run_user_code(code, time_limit_ms=5000, memory_limit_mb=256)
    assert r.status == "RE"
    # 64KB cap + 마커 길이 정도의 슬랙
    assert len(r.stderr) <= 64 * 1024 + 8192 + 200
    assert "__JCQ_OUTPUT_LIMIT_EXCEEDED__" in r.stderr


def test_modest_output_not_capped():
    """수십 KB 정상 출력은 손실 없어야 함."""
    code = "print('x' * 5000)"
    r = run_user_code(code, time_limit_ms=2000, memory_limit_mb=128)
    assert r.status == "OK"
    assert r.stdout.rstrip("\n") == "x" * 5000
