import json
import statistics

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ...config import (
    ENSEMBLE_MODELS,
    ENSEMBLE_NUM_CTX,
    ENSEMBLE_TEMPERATURE,
    JUDGE_PASS_THRESHOLD,
    JUDGE_SAMPLES,
    JUDGE_SELFCONSIST_TEMP,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
)
from ...llm import make_chat_model
from ...schemas import AuthoringState
from ..prompts import JUDGE_QUALITY_SYSTEM, JUDGE_QUALITY_USER

# 채점 앙상블과 동일한 3 판사 — 역할은 학생 코드 채점이 아니라 문제 품질 심사 (env로 설정)
_QUALITY_JUDGES = ENSEMBLE_MODELS

# self-consistency가 켜지면(JUDGE_SAMPLES>1) 약간의 온도를 줘야 샘플이 갈린다.
_N_SAMPLES = max(1, JUDGE_SAMPLES)
_SAMPLE_TEMP = ENSEMBLE_TEMPERATURE if _N_SAMPLES == 1 else JUDGE_SELFCONSIST_TEMP


# 판사 issues 정제 파라미터 — 작은 모델이 issues 필드에 넣는 노이즈를 거른다.
_MAX_ISSUES = 8
_ISSUE_MIN_LEN = 4   # 이보다 짧으면 의미 없는 파편("음", "n/a")
_ISSUE_MAX_LEN = 120  # 이보다 길면 장황한 환각/문단


def _clean_issues(issues: list) -> list[str]:
    """3-judge가 낸 issues 합을 정제한다.

    - 문자열이 아니거나 공백뿐이면 제거
    - '오류:' 접두(파싱 실패 except 분기 산출물)는 품질 이슈가 아니므로 제거
    - 길이 이상치(너무 짧음/너무 김 = 파편·환각) 제거
    - 대소문자 무시 중복 제거(순서 보존), 최대 _MAX_ISSUES개
    점수/통과 판정은 별도 필드라 영향받지 않고, 대시보드 표시용 노이즈만 줄인다."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in issues:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s or s.startswith("오류:"):
            continue
        if len(s) < _ISSUE_MIN_LEN or len(s) > _ISSUE_MAX_LEN:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= _MAX_ISSUES:
            break
    return out


def _parse_judge_response(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return json.loads(text.strip())


def _build_user_msg(candidate: dict) -> str:
    rubric = candidate.get("intent_rubric", {})
    test_cases = candidate.get("test_cases", [])
    tc_lines = [
        f"케이스 {tc.get('ordinal', i+1)} "
        f"({'sample' if tc.get('is_sample') else 'hidden'}): "
        f"stdin={repr(tc.get('stdin', '')[:60])}"
        for i, tc in enumerate(test_cases)
    ]
    tc_summary = "\n".join(tc_lines) or "(없음)"
    return JUDGE_QUALITY_USER.format(
        title=candidate.get("title", ""),
        statement=candidate.get("statement", ""),
        expected_approach=rubric.get("expected_approach", ""),
        expected_complexity=rubric.get("expected_complexity", ""),
        key_insight=rubric.get("key_insight", ""),
        must_handle=", ".join(rubric.get("must_handle", [])),
        forbidden_patterns=", ".join(rubric.get("forbidden_patterns", [])),
        test_cases_summary=tc_summary,
    )


def _poll_one_judge(judge_id: str, model: str, user_msg: str) -> dict:
    """한 판사를 _N_SAMPLES회 샘플해 판사 내부에서 합산한다.

    passed = 샘플 다수결, score = 샘플 중앙값. 대표 rationale/issues는 중앙값에
    가장 가까운 샘플에서 취한다. JUDGE_SAMPLES=1이면 기존 단일 호출과 동일.
    """
    llm = make_chat_model(
        model,
        temperature=_SAMPLE_TEMP,
        json_mode=True,
        num_ctx=ENSEMBLE_NUM_CTX,
    )

    samples: list[dict] = []
    for s in range(_N_SAMPLES):
        try:
            resp = llm.invoke(
                [
                    SystemMessage(content=JUDGE_QUALITY_SYSTEM),
                    HumanMessage(content=user_msg),
                ],
                config=RunnableConfig(run_name=f"judge_quality/{judge_id}#{s+1}"),
            )
            result = _parse_judge_response(resp.content)
            samples.append(
                {
                    "passed": bool(result.get("passed", False)),
                    "score": float(result.get("score", 0.0)),
                    "issues": list(result.get("issues", [])),
                    "rationale": result.get("rationale", ""),
                }
            )
        except Exception as exc:
            samples.append(
                {"passed": False, "score": 0.0, "issues": [f"오류: {exc}"], "rationale": ""}
            )

    scores = [s["score"] for s in samples]
    median_score = statistics.median(scores)
    n_pass = sum(1 for s in samples if s["passed"])
    judge_passed = n_pass * 2 > _N_SAMPLES  # 엄격 다수결 (동수는 실패)

    # 대표 샘플 = 중앙값에 가장 가까운 score를 낸 샘플.
    rep = min(samples, key=lambda s: abs(s["score"] - median_score))
    return {
        "judge_id": judge_id,
        "passed": judge_passed,
        "score": median_score,
        "issues": rep["issues"],
        "rationale": rep["rationale"],
    }


def _judge_one_candidate(candidate: dict) -> dict:
    """3-judge 앙상블로 문제 품질을 심사. 2/3 이상 pass + 점수 중앙값 ≥ threshold면 통과.

    집계를 평균 대신 중앙값으로 둬 판사 한 명의 이상치(0점 오류 등)에 강건하게 만든다.
    """
    user_msg = _build_user_msg(candidate)
    per_judge = [
        _poll_one_judge(judge_id, model, user_msg)
        for judge_id, model in _QUALITY_JUDGES
    ]

    judge_scores = [j["score"] for j in per_judge]
    median_score = statistics.median(judge_scores) if judge_scores else 0.0
    n_passed = sum(1 for j in per_judge if j["passed"])
    judge_passed = n_passed >= 2 and median_score >= JUDGE_PASS_THRESHOLD

    all_issues: list[str] = []
    for j in per_judge:
        all_issues.extend(j["issues"])

    return {
        "judge_passed": judge_passed,
        "judge_score": round(median_score, 3),
        "judge_scores": [round(s, 3) for s in judge_scores],
        "judge_rationale": " | ".join(
            f"[{j['judge_id']}] {j['rationale']}" for j in per_judge
        ),
        "judge_issues": _clean_issues(all_issues),
    }


def judge_candidates(state: AuthoringState) -> dict:
    """verify_passed된 candidate만 LLM 품질 심사를 수행한다."""
    updated: list[dict] = []
    for c in state["candidates"]:
        c = dict(c)
        if c.get("verify_passed"):
            c.update(_judge_one_candidate(c))
        updated.append(c)
    return {"candidates": updated}
