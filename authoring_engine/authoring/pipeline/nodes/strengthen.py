import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama

from ...backend_client import sandbox_run
from ...config import (
    AUTHOR_RETRY_TEMPERATURE,
    ENSEMBLE_MODELS,
    ENSEMBLE_NUM_CTX,
    PERF_RATIO,
    STRENGTHEN_ENABLED,
    STRENGTHEN_INPUTS_PER_ATTACK,
    STRENGTHEN_MAX_ATTEMPTS,
)
from ...llm import make_chat_model
from ...schemas import AuthoringState
from ..prompts import STRENGTHEN_SYSTEM, STRENGTHEN_USER

# 입력 생성도 attack과 같은 Melchior 단독. 결정론(0)이면 같은 입력만 나와 보강이 안 되므로
# verify 재시도와 같은 약한 온도를 줘 다양한 입력을 끌어낸다.
_STRENGTHEN_MODEL = ENSEMBLE_MODELS[0]


def _parse_inputs(text: str) -> list[str]:
    """LLM 출력에서 stdin 페이로드 리스트를 추출. {"inputs": [...]} 또는 [...] 모두 허용."""
    t = text.strip()
    if t.startswith("```"):
        t = "\n".join(t.split("\n")[1:])
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    try:
        obj = json.loads(t.strip())
    except (json.JSONDecodeError, ValueError):
        return []
    raw = obj.get("inputs", []) if isinstance(obj, dict) else obj
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if isinstance(x, (str, int, float))]


def _is_discriminating(
    reference_code: str,
    attack_code: str,
    stdin: str,
    *,
    time_limit_ms: int,
    memory_limit_mb: int,
) -> tuple[bool, str | None]:
    """정답(reference)과 공격(attack)을 같은 입력에 돌려 판별 가능 여부를 본다.

    판별 성공 조건: 정답이 제한 시간(PERF_RATIO) 안에 정상 종료(OK)하면서, 공격이
    비정상 종료(TLE/MLE/RE)하거나 정답과 다른 출력을 내는 경우. 이 입력을 테스트에
    추가하면 그 공격은 다음 attack에서 표적 차원으로 탈락한다.

    return: (판별 성공 여부, 성공 시 expected_stdout=정답 출력)
    """
    ref = sandbox_run(
        reference_code, stdin, time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb
    )
    # 정답이 비정상이거나 제한 시간을 못 지키면 유효한 테스트 입력이 아니다(reference가 기준).
    if ref.status != "OK" or ref.elapsed_ms > time_limit_ms * PERF_RATIO:
        return False, None

    atk = sandbox_run(
        attack_code, stdin, time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb
    )
    expected = ref.stdout.rstrip()
    if atk.status != "OK" or atk.stdout.rstrip() != expected:
        return True, expected
    return False, None


def _strengthen_one(candidate: dict, llm: ChatOllama) -> dict:
    """한 후보의 미검출 공격을 표적으로 판별 테스트를 생성·검증·추가한다."""
    reference_code = candidate.get("reference_code", "")
    attempts = candidate.get("strengthen_attempts", 0) + 1
    # reference가 없으면(레거시/폐기) 정답 기준이 없어 보강 불가 — 시도 수만 올려 루프 종료 유도.
    if not reference_code:
        return {"strengthen_added": 0, "strengthen_attempts": attempts}

    time_limit_ms = candidate["time_limit_ms"]
    memory_limit_mb = candidate["memory_limit_mb"]
    rubric = candidate.get("intent_rubric", {})

    test_cases = list(candidate.get("test_cases", []))
    seen = {(tc.get("stdin", "") or "").rstrip() for tc in test_cases}
    next_ordinal = max((tc.get("ordinal", 0) for tc in test_cases), default=0) + 1

    # 표적 차원으로 못 걸러낸(=rejected_on_target False) 공격만 — 코드가 있어야 oracle로 쓴다.
    uncaught = [
        r
        for r in candidate.get("attack_results", [])
        if r.get("code") and r.get("rejected_on_target") is False
    ]

    added = 0
    notes: list[str] = []
    for atk in uncaught:
        strategy = atk.get("strategy", "edge_skip")
        attack_code = atk["code"]
        try:
            resp = llm.invoke(
                [
                    SystemMessage(content=STRENGTHEN_SYSTEM),
                    HumanMessage(
                        content=STRENGTHEN_USER.format(
                            strategy=strategy,
                            n=STRENGTHEN_INPUTS_PER_ATTACK,
                            title=candidate.get("title", ""),
                            statement=candidate.get("statement", ""),
                            expected_complexity=rubric.get("expected_complexity", ""),
                            must_handle=", ".join(rubric.get("must_handle", [])),
                        )
                    ),
                ],
                config=RunnableConfig(run_name=f"strengthen/{strategy}"),
            )
            candidate_inputs = _parse_inputs(resp.content)
        except Exception:
            candidate_inputs = []

        added_this = 0
        for stdin in candidate_inputs:
            if not stdin:
                continue
            if not stdin.endswith("\n"):
                stdin = stdin + "\n"
            if stdin.rstrip() in seen:
                continue
            ok, expected = _is_discriminating(
                reference_code,
                attack_code,
                stdin,
                time_limit_ms=time_limit_ms,
                memory_limit_mb=memory_limit_mb,
            )
            if ok:
                test_cases.append(
                    {
                        "ordinal": next_ordinal,
                        "stdin": stdin,
                        "expected_stdout": expected,
                        "is_sample": False,  # 보강 테스트는 항상 hidden
                    }
                )
                seen.add(stdin.rstrip())
                next_ordinal += 1
                added += 1
                added_this += 1
        notes.append(f"{strategy}+{added_this}")

    return {
        "test_cases": test_cases,
        "strengthen_added": added,
        "strengthen_attempts": attempts,
        "strengthen_note": ", ".join(notes),
    }


def strengthen_tests(state: AuthoringState) -> dict:
    """변별력 미달 후보의 테스트를 보강한다(attack→strengthen→attack 루프의 보강 단계).

    표적 차원으로 못 걸러낸 공격을 oracle 삼아, 그 공격이 틀리고 정답은 맞는 '판별 입력'을
    생성·검증해 test_cases에 추가한다. 추가 후 그래프는 attack_candidates로 되돌아가 강화된
    테스트셋으로 재검증한다. JCQ_STRENGTHEN_ENABLED=0이면 no-op(라우터가 진입을 막는다).

    보강 대상: solver_passed && 변별력 미통과 && strengthen_attempts < STRENGTHEN_MAX_ATTEMPTS.
    """
    if not STRENGTHEN_ENABLED:
        return {"candidates": list(state["candidates"])}

    # 재시도 온도 — 같은 입력만 반복 생성되는 걸 피한다.
    llm = make_chat_model(
        _STRENGTHEN_MODEL[1],
        temperature=AUTHOR_RETRY_TEMPERATURE,
        json_mode=True,
        num_ctx=ENSEMBLE_NUM_CTX,
    )

    updated: list[dict] = []
    for c in state["candidates"]:
        c = dict(c)
        if (
            c.get("solver_passed")
            and not c.get("discrimination_passed", True)
            and c.get("strengthen_attempts", 0) < STRENGTHEN_MAX_ATTEMPTS
        ):
            c.update(_strengthen_one(c, llm))
        updated.append(c)
    return {"candidates": updated}
