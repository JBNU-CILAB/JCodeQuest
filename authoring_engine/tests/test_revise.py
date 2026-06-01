"""revise_problem 노드 + judge 라우터 단위 테스트 (Ollama 불필요).

revise는 2-call(REVISE → author_solution)이라 LLM 응답을 큐로 두 개 미리 넣어 둔다.
라우터 테스트는 후보 상태만으로 결과를 검증한다(LLM 호출 없음).
"""
import json
from types import SimpleNamespace

from authoring import config
from authoring.pipeline import graph as graph_mod
from authoring.pipeline.nodes import revise as revise_mod


# ── 헬퍼 ────────────────────────────────────────────────────────────────────
def _rubric(**over):
    base = {
        "expected_approach": "그리디로 한 번 훑어 답을 갱신",
        "expected_complexity": "O(n)",
        "must_handle": ["빈 입력", "음수"],
        "forbidden_patterns": ["O(n^2) 이중 루프"],
        "key_insight": "최댓값 갱신은 단조 누적이면 충분",
        "one_line_summary": "n*2 출력",
    }
    base.update(over)
    return base


def _candidate(**over):
    c = {
        "index": 0,
        "category": "basic",
        "level": "bronze",
        "time_limit_ms": 1000,
        "memory_limit_mb": 128,
        "title": "원본",
        "statement": "정수 n을 입력받아 2*n을 출력하라.",
        "intent_rubric": _rubric(),
        "reference_code": "n=int(input())\nprint(n*2)\n",
        "test_inputs": [{"ordinal": 1, "stdin": "1\n", "is_sample": True}],
        "test_cases": [{"ordinal": 1, "stdin": "1\n", "expected_stdout": "2", "is_sample": True}],
        "verify_passed": True,
        "judge_passed": False,
        "judge_issues": ["테스트가 must_handle('음수')을 커버하지 않음"],
        "judge_rationale": "음수 입력에 대한 검증이 부족함",
        "revise_attempts": 0,
        "revise_history": [],
    }
    c.update(over)
    return c


class _QueueLLM:
    """invoke가 호출될 때마다 큐에서 다음 응답을 꺼낸다(없으면 RuntimeError)."""

    def __init__(self, responses):
        self._q = list(responses)
        self.calls = 0

    def invoke(self, *_a, **_k):
        self.calls += 1
        if not self._q:
            raise RuntimeError("응답 큐 소진")
        r = self._q.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(content=r)


def _revise_response(**over):
    """REVISE 1차 호출이 돌려줄 JSON 문자열 (DRAFT 스키마와 동일)."""
    draft = {
        "title": "수정된 제목",
        "statement": "정수 n을 입력받아 2*n을 출력하라. 음수 입력도 처리한다.",
        "intent_rubric": _rubric(must_handle=["빈 입력", "음수", "0"]),
    }
    draft.update(over)
    return json.dumps(draft, ensure_ascii=False)


def _reauthor_response(**over):
    """author_solution 2차 호출이 돌려줄 JSON 문자열."""
    sol = {
        "reference_code": "n=int(input())\nprint(n*2)\n",
        "test_inputs": [
            {"ordinal": 1, "stdin": "3\n", "is_sample": True},
            {"ordinal": 2, "stdin": "0\n", "is_sample": False},
            {"ordinal": 3, "stdin": "-5\n", "is_sample": False},
            {"ordinal": 4, "stdin": "100\n", "is_sample": False},
            {"ordinal": 5, "stdin": "-100\n", "is_sample": False},
        ],
    }
    sol.update(over)
    return json.dumps(sol, ensure_ascii=False)


# ── _revise_one 단위 ───────────────────────────────────────────────────────
def test_revise_one_success_resets_gates_and_bumps_attempts():
    llm = _QueueLLM([_revise_response(), _reauthor_response()])
    out = revise_mod._revise_one(_candidate(), llm)

    # 본문 갱신
    assert out["title"] == "수정된 제목"
    assert "음수 입력도 처리한다" in out["statement"]
    assert "0" in out["intent_rubric"]["must_handle"]
    assert out["reference_code"].startswith("n=int(input())")
    assert len(out["test_inputs"]) == 5
    # 다운스트림 게이트 리셋(verify가 다시 test_cases를 채우고 judge가 재평가)
    assert out["verify_passed"] is False
    assert out["judge_passed"] is False
    assert out["test_cases"] == []
    # 카운터 + 히스토리
    assert out["revise_attempts"] == 1
    assert out["revise_history"][-1]["attempt"] == 1
    assert out["revise_history"][-1]["note"] == "revised"
    assert out["revise_history"][-1]["issues_in"] == [
        "테스트가 must_handle('음수')을 커버하지 않음"
    ]
    assert llm.calls == 2  # REVISE + author_solution


def test_revise_one_llm_error_preserves_body_and_bumps_attempts():
    llm = _QueueLLM([RuntimeError("ollama down")])
    c = _candidate()
    out = revise_mod._revise_one(c, llm)

    # 본문 보존 — 어떤 필드도 변경 X
    assert out["title"] == c["title"]
    assert out["statement"] == c["statement"]
    assert out["reference_code"] == c["reference_code"]
    assert out["test_cases"] == c["test_cases"]
    assert out["verify_passed"] is True  # 그대로
    # 카운터는 증가(루프 자연 종료)
    assert out["revise_attempts"] == 1
    assert out["revise_history"][-1]["note"].startswith("error:")


def test_revise_one_reauthor_empty_treated_as_failure():
    # REVISE는 성공했지만 author_solution이 빈 reference_code → 본문 미변경 + 에러 기록
    llm = _QueueLLM([_revise_response(), _reauthor_response(reference_code="")])
    c = _candidate()
    out = revise_mod._revise_one(c, llm)

    assert out["title"] == c["title"]                # 본문 보존
    assert out["judge_passed"] is False              # 그대로
    assert out["revise_attempts"] == 1
    assert out["revise_history"][-1]["note"].startswith("error:")


# ── revise_problem 노드 (eligibility 필터) ────────────────────────────────
def test_revise_node_skips_ineligible_candidates(monkeypatch):
    """이미 통과/이슈 없음/시도 소진/verify 실패는 LLM을 호출하지 않는다."""
    calls: list[dict] = []

    def fake_revise_one(c, _llm):
        calls.append(c)
        out = dict(c)
        out["revise_attempts"] = (c.get("revise_attempts") or 0) + 1
        return out

    monkeypatch.setattr(revise_mod, "_revise_one", fake_revise_one)
    # make_chat_model이 실제로 호출돼도 무방하지만 외부 의존 차단
    monkeypatch.setattr(revise_mod, "make_chat_model",
                        lambda *_a, **_k: object())

    state = {
        "candidates": [
            _candidate(index=0),                                            # 적격
            _candidate(index=1, judge_passed=True),                         # 이미 통과
            _candidate(index=2, judge_issues=[]),                           # 이슈 없음
            _candidate(index=3, revise_attempts=config.REVISE_MAX_ATTEMPTS),# 소진
            _candidate(index=4, verify_passed=False),                       # verify 실패
        ]
    }
    out = revise_mod.revise_problem(state)
    touched = {c["index"] for c in calls}
    assert touched == {0}


# ── _route_after_judge 라우터 ───────────────────────────────────────────────
def test_route_after_judge_routes_to_revise_when_failures_with_room():
    state = {"candidates": [
        _candidate(judge_passed=True),                            # 통과자도 있음
        _candidate(judge_passed=False, revise_attempts=0),        # 보강 여유
    ]}
    # 실패자 우선 — 통과자가 있어도 revise로 간다.
    assert graph_mod._route_after_judge(state) == "revise"


def test_route_after_judge_continues_when_all_failures_exhausted():
    state = {"candidates": [
        _candidate(judge_passed=True),
        _candidate(judge_passed=False, revise_attempts=config.REVISE_MAX_ATTEMPTS),
    ]}
    # 모든 실패자가 소진 → 통과자 있으면 진행.
    assert graph_mod._route_after_judge(state) == "continue"


def test_route_after_judge_ends_when_nothing_alive():
    state = {"candidates": [
        _candidate(verify_passed=False, judge_passed=False),
    ]}
    assert graph_mod._route_after_judge(state) == "end"


def test_route_after_judge_ends_when_no_pass_and_no_revise_room():
    state = {"candidates": [
        _candidate(judge_passed=False, revise_attempts=config.REVISE_MAX_ATTEMPTS),
    ]}
    # verify_passed지만 통과자 0 + 보강도 못함 → END.
    assert graph_mod._route_after_judge(state) == "end"


def test_route_after_judge_skips_revise_when_no_issues():
    state = {"candidates": [
        _candidate(judge_passed=True),
        _candidate(judge_passed=False, judge_issues=[]),  # 이슈 없으면 revise 불가
    ]}
    assert graph_mod._route_after_judge(state) == "continue"
