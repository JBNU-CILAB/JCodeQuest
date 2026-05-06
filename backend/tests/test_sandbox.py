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
