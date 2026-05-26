import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama

from ...backend_client import sandbox_run
from ...config import (
    DISCRIMINATION_ATTACKS,
    DISCRIMINATION_ENABLED,
    DISCRIMINATION_MIN_REJECT,
    ENSEMBLE_MODELS,
    ENSEMBLE_NUM_CTX,
    ENSEMBLE_TEMPERATURE,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    SOLVER_SAMPLE_LIMIT,
)
from ...schemas import AuthoringState
from ..prompts import ATTACK_SYSTEM, ATTACK_USER

# 공격 풀이는 결함을 '그럴듯하게' 심어야 하므로 가장 유능한 코더 모델(Melchior) 단독 사용.
# solver처럼 3-LLM을 다 돌릴 필요는 없다 — 변별력은 '하나라도 약점을 뚫으면' 드러난다.
_ATTACK_MODEL = ENSEMBLE_MODELS[0]

# 공격 전략 — rubric 표적. ATTACK_SYSTEM의 전략명과 일치해야 한다.
_STRATEGIES = ["naive", "edge_skip"]


def _extract_code(text: str) -> str:
    """마크다운 펜스를 제거하고 Python 코드만 추출 (solver와 동일 규칙)."""
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _sample_text(candidate: dict) -> str:
    sample_cases = [tc for tc in candidate.get("test_cases", []) if tc.get("is_sample")]
    parts = [
        f"입력:\n{tc.get('stdin', '')}\n출력:\n{tc.get('expected_stdout', '')}"
        for tc in sample_cases[:SOLVER_SAMPLE_LIMIT]
    ]
    return "\n\n".join(parts) or "(샘플 없음)"


def _run_against_tests(code: str, candidate: dict) -> tuple[str, str]:
    """공격 코드를 전체 test_cases에 돌려 (verdict, rationale) 반환.

    verdict: AC(전부 통과) / WA / TLE / MLE / RE.
    AC면 테스트가 이 결함을 못 걸러낸 것 → 변별력 약함의 증거.
    """
    test_cases = candidate.get("test_cases", [])
    time_limit_ms = candidate["time_limit_ms"]
    memory_limit_mb = candidate["memory_limit_mb"]

    passed = 0
    total = len(test_cases)
    for tc in test_cases:
        result = sandbox_run(
            code,
            tc.get("stdin", ""),
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
        )
        if result.status == "TLE":
            return "TLE", "시간 초과로 탈락"
        if result.status in ("MLE", "RE"):
            return result.status, result.stderr[:200]
        if result.status == "OK" and result.stdout.rstrip() == tc.get(
            "expected_stdout", ""
        ).rstrip():
            passed += 1

    if total > 0 and passed == total:
        return "AC", f"{passed}/{total} 통과 — 테스트가 결함을 못 걸러냄"
    return "WA", f"{passed}/{total} 통과 — 테스트가 결함을 걸러냄"


def _attack_one(candidate: dict, strategy: str, llm: ChatOllama) -> dict:
    """단일 전략으로 결함 풀이를 생성·실행한다."""
    rubric = candidate.get("intent_rubric", {})
    try:
        resp = llm.invoke(
            [
                SystemMessage(content=ATTACK_SYSTEM),
                HumanMessage(
                    content=ATTACK_USER.format(
                        strategy=strategy,
                        title=candidate.get("title", ""),
                        statement=candidate.get("statement", ""),
                        expected_complexity=rubric.get("expected_complexity", ""),
                        must_handle=", ".join(rubric.get("must_handle", [])),
                        forbidden_patterns=", ".join(
                            rubric.get("forbidden_patterns", [])
                        ),
                        sample_cases=_sample_text(candidate),
                    )
                ),
            ],
            config=RunnableConfig(run_name=f"attack/{strategy}"),
        )
        code = _extract_code(resp.content)
    except Exception as exc:
        # LLM 자체 실패 — 유효한 공격이 아니므로 분모에서 제외(fail-open).
        return {
            "strategy": strategy,
            "verdict": "ERROR",
            "rejected": None,
            "code": "",
            "rationale": str(exc),
        }

    if not code:
        return {
            "strategy": strategy,
            "verdict": "ERROR",
            "rejected": None,
            "code": "",
            "rationale": "공격 코드 생성 실패(빈 출력)",
        }

    verdict, rationale = _run_against_tests(code, candidate)
    return {
        "strategy": strategy,
        "verdict": verdict,
        "rejected": verdict != "AC",  # 테스트가 결함을 걸러냈으면 True
        "code": code,
        "rationale": rationale,
    }


def _discriminate_one(candidate: dict, llm: ChatOllama) -> dict:
    n = max(1, DISCRIMINATION_ATTACKS)
    strategies = [_STRATEGIES[i % len(_STRATEGIES)] for i in range(n)]
    results = [_attack_one(candidate, s, llm) for s in strategies]

    valid = [r for r in results if r["rejected"] is not None]
    rejected = sum(1 for r in valid if r["rejected"])

    if not valid:
        # 모든 공격 LLM이 실패 → 변별력을 판단할 수 없으므로 통과시킨다(fail-open).
        return {
            "attack_results": results,
            "discrimination_score": None,
            "discrimination_passed": True,
        }

    return {
        "attack_results": results,
        "discrimination_score": round(rejected / len(valid), 3),
        "discrimination_passed": rejected >= DISCRIMINATION_MIN_REJECT,
    }


def attack_candidates(state: AuthoringState) -> dict:
    """solver_passed된 후보에 결함 풀이를 던져 테스트 변별력을 검사한다.

    테스트가 최소 DISCRIMINATION_MIN_REJECT개의 공격을 탈락(non-AC)시켜야 통과.
    0개 탈락 = 어떤 결함도 못 걸러내는 약한 테스트셋 → 폐기.
    JCQ_DISCRIMINATION_ENABLED=0이면 노드를 no-op으로 건너뛴다(통과 처리).
    """
    if not DISCRIMINATION_ENABLED:
        return {"candidates": list(state["candidates"])}

    llm = ChatOllama(
        model=_ATTACK_MODEL[1],
        temperature=ENSEMBLE_TEMPERATURE,
        base_url=OLLAMA_BASE_URL,
        num_ctx=ENSEMBLE_NUM_CTX,
        keep_alive=OLLAMA_KEEP_ALIVE,
    )

    updated: list[dict] = []
    for c in state["candidates"]:
        c = dict(c)
        if c.get("solver_passed"):
            c.update(_discriminate_one(c, llm))
        updated.append(c)
    return {"candidates": updated}
