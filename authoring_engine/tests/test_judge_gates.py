"""출제 파이프라인 게이트 개선 단위 테스트 (Ollama 불필요).

LLM/sandbox 호출은 전부 callsite(노드 모듈)에서 monkeypatch하므로 외부 의존성이 없다.
pytest가 있으면 `pytest tests/test_judge_gates.py`, 없으면
`.venv/bin/python tests/test_judge_gates.py`로 실행된다.
"""
from types import SimpleNamespace

from authoring.pipeline.nodes import attack, compare, judge, persist


# ── 헬퍼 ────────────────────────────────────────────────────────────────────
def _candidate(**over):
    c = {
        "title": "t",
        "statement": "s",
        "intent_rubric": {
            "expected_complexity": "O(n)",
            "must_handle": ["빈 입력"],
            "forbidden_patterns": ["O(n^2) 이중 루프"],
        },
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "test_cases": [
            {"ordinal": 1, "stdin": "1\n", "expected_stdout": "1", "is_sample": True},
            {"ordinal": 2, "stdin": "2\n", "expected_stdout": "2", "is_sample": False},
        ],
        "solver_passed": True,
    }
    c.update(over)
    return c


class _FakeLLM:
    """invoke가 항상 같은 code를 돌려주는 가짜 ChatOllama."""

    def __init__(self, content="print(1)", raise_exc=False):
        self._content = content
        self._raise = raise_exc

    def invoke(self, *a, **k):
        if self._raise:
            raise RuntimeError("llm down")
        return SimpleNamespace(content=self._content)


# ── compare 게이트 (순수 함수) ──────────────────────────────────────────────
def test_compare_gate_thresholds():
    assert compare.COMPARE_GATE_ENABLED  # 기본 on
    assert compare._passes_compare_gate(0.3, 0.6) is True      # 정상
    assert compare._passes_compare_gate(0.7, 0.6) is False     # 환각 과다
    assert compare._passes_compare_gate(0.3, 0.2) is False     # 의도 이탈
    # 경계값: <= / >= 포함
    assert compare._passes_compare_gate(0.5, 0.4) is True


def test_compare_gate_disabled(monkeypatch=None):
    orig = compare.COMPARE_GATE_ENABLED
    compare.COMPARE_GATE_ENABLED = False
    try:
        # 게이트 off면 어떤 점수든 통과
        assert compare._passes_compare_gate(0.99, 0.0) is True
    finally:
        compare.COMPARE_GATE_ENABLED = orig


# ── attack(변별력) 게이트 ───────────────────────────────────────────────────
def _patch_sandbox(monkey_target, *, match_expected):
    """sandbox_run을 대체: match_expected면 expected_stdout 그대로 반환(AC), 아니면 WA."""
    def fake(code, stdin, *, time_limit_ms, memory_limit_mb):
        # 어떤 stdin에 대해서도 첫 expected를 흉내. match_expected=True면 정답처럼.
        out = "1" if match_expected else "WRONG"
        return SimpleNamespace(status="OK", stdout=out, stderr="", elapsed_ms=1)
    attack.sandbox_run = fake


def test_attack_rejects_weak_when_tests_catch():
    # 테스트가 결함 풀이를 걸러냄(WA) → discrimination_passed True
    _patch_sandbox(attack, match_expected=False)
    out = attack._discriminate_one(_candidate(), _FakeLLM())
    assert out["discrimination_passed"] is True
    assert out["discrimination_score"] == 1.0
    assert all(r["rejected"] for r in out["attack_results"])


def test_attack_fails_when_tests_too_weak():
    # 결함 풀이가 전부 AC(테스트가 못 걸러냄) → discrimination_passed False
    # 단, expected_stdout이 케이스마다 다르므로 '항상 1 반환'은 케이스2(=2)에서 틀림.
    # 모든 케이스를 통과시키려면 expected와 같은 값을 줘야 하므로 별도 fake 사용.
    def fake(code, stdin, *, time_limit_ms, memory_limit_mb):
        # stdin "1\n"->expected "1", "2\n"->expected "2": stdin 첫 글자를 그대로 출력해 항상 AC
        return SimpleNamespace(status="OK", stdout=stdin.strip(), stderr="", elapsed_ms=1)
    attack.sandbox_run = fake
    out = attack._discriminate_one(_candidate(), _FakeLLM())
    assert out["discrimination_passed"] is False
    assert out["discrimination_score"] == 0.0


def test_attack_fail_open_when_llm_errors():
    # 공격 LLM이 전부 실패 → 변별력 판단 불가 → fail-open(통과), score None
    out = attack._discriminate_one(_candidate(), _FakeLLM(raise_exc=True))
    assert out["discrimination_passed"] is True
    assert out["discrimination_score"] is None
    assert all(r["verdict"] == "ERROR" for r in out["attack_results"])


def test_attack_node_skips_unsolved():
    # solver_passed=False면 공격을 돌리지 않는다(필드 미설정).
    state = {"candidates": [_candidate(solver_passed=False)]}
    out = attack.attack_candidates(state)
    assert "discrimination_passed" not in out["candidates"][0]


# ── judge 중앙값 집계 + 게이트 ──────────────────────────────────────────────
def _patch_poll(results):
    seq = iter(results)
    judge._poll_one_judge = lambda jid, model, msg: next(seq)


def test_judge_median_pass():
    # 점수 [0.9,0.8,0.2], pass [T,T,F] → median 0.8, n_pass 2 → 통과
    _patch_poll([
        {"judge_id": "Melchior", "passed": True, "score": 0.9, "issues": [], "rationale": "a"},
        {"judge_id": "Balthasar", "passed": True, "score": 0.8, "issues": [], "rationale": "b"},
        {"judge_id": "Casper", "passed": False, "score": 0.2, "issues": ["x"], "rationale": "c"},
    ])
    out = judge._judge_one_candidate(_candidate())
    assert out["judge_passed"] is True
    assert out["judge_score"] == 0.8
    assert out["judge_scores"] == [0.9, 0.8, 0.2]


def test_judge_median_robust_to_outlier():
    # 점수 [0.0,0.8,0.85] (한 판사 0점 오류), pass [F,T,T] → median 0.8 (평균이면 0.55라 탈락).
    _patch_poll([
        {"judge_id": "Melchior", "passed": False, "score": 0.0, "issues": ["오류"], "rationale": ""},
        {"judge_id": "Balthasar", "passed": True, "score": 0.8, "issues": [], "rationale": "b"},
        {"judge_id": "Casper", "passed": True, "score": 0.85, "issues": [], "rationale": "c"},
    ])
    out = judge._judge_one_candidate(_candidate())
    assert out["judge_passed"] is True
    assert out["judge_score"] == 0.8


def test_judge_fails_below_threshold():
    # median 0.6 < 0.7 → 탈락 (n_pass와 무관)
    _patch_poll([
        {"judge_id": "Melchior", "passed": True, "score": 0.9, "issues": [], "rationale": ""},
        {"judge_id": "Balthasar", "passed": False, "score": 0.6, "issues": [], "rationale": ""},
        {"judge_id": "Casper", "passed": False, "score": 0.5, "issues": [], "rationale": ""},
    ])
    out = judge._judge_one_candidate(_candidate())
    assert out["judge_passed"] is False


# ── persist 게이트 (3축 AND) ────────────────────────────────────────────────
def test_persist_gate_requires_all_three():
    saved = []
    persist.create_problem = lambda problem, **k: saved.append(problem.title) or len(saved)

    def cand(title, **flags):
        rubric = {
            "expected_approach": "a", "expected_complexity": "O(n)",
            "key_insight": "k", "one_line_summary": "ol",
            "must_handle": [], "forbidden_patterns": [],
        }
        base = {
            "title": title, "statement": "s", "category": "math", "level": "bronze",
            "points": 100, "time_limit_ms": 2000, "memory_limit_mb": 256,
            "reference_code": "print(1)", "intent_rubric": rubric,
            "test_cases": [{"ordinal": 1, "stdin": "1", "expected_stdout": "1", "is_sample": True}],
        }
        base.update(flags)
        return base

    state = {
        "candidates": [
            cand("all_pass", solver_passed=True, discrimination_passed=True, compare_passed=True),
            cand("no_solver", solver_passed=False, discrimination_passed=True, compare_passed=True),
            cand("no_discrim", solver_passed=True, discrimination_passed=False, compare_passed=True),
            cand("no_compare", solver_passed=True, discrimination_passed=True, compare_passed=False),
            # 신규 게이트 필드 미설정 → .get(default=True)라 solver_passed만으로 통과(하위호환)
            cand("legacy", solver_passed=True),
        ],
        "saved_problem_ids": [],
        "errors": [],
        "original_problem_id": 1,
    }
    persist.persist_approved(state)
    assert saved == ["all_pass", "legacy"]


# ── 러너 (pytest 없이도 실행) ────────────────────────────────────────────────
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")
