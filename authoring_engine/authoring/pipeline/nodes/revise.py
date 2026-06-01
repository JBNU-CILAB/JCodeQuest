"""judge_candidates 실패 후보의 statement·rubric을 판사 issues로 표적 수정하는 보강 노드.

흐름(2-call):
  1) REVISE 호출 — 현재 draft + judge_issues → 수정된 draft(title/statement/intent_rubric)
  2) author_solution 재호출 — 수정된 draft → 새 reference_code + test_inputs

수정 후 후보의 verify_passed / judge_passed / test_cases를 리셋하여 graph.py의
역방향 엣지가 verify_candidates로 돌려보내면 verify → judge 가드가 자동으로
revise된 후보만 재처리한다. revise_attempts를 1 증가시켜 라우터의 종료 조건을 만족시킨다.

Fail-safe: REVISE/author_solution 어디서 실패해도 본문을 건드리지 않고 attempts만
증가시켜 루프가 결국 종료되게 한다(무한루프 방지). attack→strengthen 루프와 같은 패턴.
"""
from __future__ import annotations

import json
import logging

from jcq_shared.schemas import IntentRubric
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama

from ...config import (
    AUTHOR_MODEL,
    AUTHOR_NUM_CTX,
    AUTHOR_RETRY_TEMPERATURE,
    REVISE_ENABLED,
    REVISE_MAX_ATTEMPTS,
)
from ...llm import make_chat_model
from ...schemas import AuthoringState
from ..prompts import REVISE_SYSTEM, REVISE_USER, SOLUTION_SYSTEM, SOLUTION_USER

log = logging.getLogger(__name__)


def _clean_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return json.loads(text.strip())


def _format_issues_block(issues: list[str]) -> str:
    if not issues:
        return "(이슈 목록 없음 — rationale을 단서로 명확성·테스트 충분성을 보강할 것)"
    return "\n".join(f"- {s}" for s in issues)


def _revise_draft(candidate: dict, llm: ChatOllama, attempt_no: int) -> dict:
    """REVISE 1회 호출. 성공 시 검증된 {title, statement, intent_rubric}, 실패 시 예외."""
    rubric = candidate.get("intent_rubric", {})
    issues = candidate.get("judge_issues", []) or []
    rationale = candidate.get("judge_rationale", "") or "(없음)"

    resp = llm.invoke(
        [
            SystemMessage(content=REVISE_SYSTEM),
            HumanMessage(
                content=REVISE_USER.format(
                    category=candidate.get("category", ""),
                    level=candidate.get("level", ""),
                    time_limit_ms=candidate.get("time_limit_ms", 0),
                    memory_limit_mb=candidate.get("memory_limit_mb", 0),
                    title=candidate.get("title", ""),
                    statement=candidate.get("statement", ""),
                    expected_approach=rubric.get("expected_approach", ""),
                    expected_complexity=rubric.get("expected_complexity", ""),
                    must_handle=", ".join(rubric.get("must_handle", [])),
                    forbidden_patterns=", ".join(rubric.get("forbidden_patterns", [])),
                    key_insight=rubric.get("key_insight", ""),
                    one_line_summary=rubric.get("one_line_summary", ""),
                    issues_block=_format_issues_block(issues),
                    judge_rationale=rationale[:1200],
                    attempt=attempt_no,
                    max_attempts=REVISE_MAX_ATTEMPTS,
                )
            ),
        ],
        config=RunnableConfig(run_name=f"revise_problem#{attempt_no}"),
    )
    draft = _clean_json(resp.content)
    new_rubric = draft.get("intent_rubric", {})
    IntentRubric.model_validate(new_rubric)  # 실패 시 예외 → 호출 측이 fail-safe로 흡수
    return draft


def _reauthor_solution(candidate: dict, llm: ChatOllama) -> tuple[str, list[dict]]:
    """수정된 draft로 author_solution 재호출 → (reference_code, test_inputs)."""
    rubric = candidate.get("intent_rubric", {})
    resp = llm.invoke(
        [
            SystemMessage(content=SOLUTION_SYSTEM),
            HumanMessage(
                content=SOLUTION_USER.format(
                    title=candidate.get("title", ""),
                    statement=candidate.get("statement", ""),
                    expected_approach=rubric.get("expected_approach", ""),
                    key_insight=rubric.get("key_insight", ""),
                    expected_complexity=rubric.get("expected_complexity", ""),
                    must_handle=", ".join(rubric.get("must_handle", [])),
                    forbidden_patterns=", ".join(rubric.get("forbidden_patterns", [])),
                    time_limit_ms=candidate.get("time_limit_ms", 0),
                    memory_limit_mb=candidate.get("memory_limit_mb", 0),
                )
            ),
        ],
        config=RunnableConfig(run_name="revise_problem/reauthor"),
    )
    sol = _clean_json(resp.content)
    return sol.get("reference_code", ""), list(sol.get("test_inputs", []))


def _revise_one(candidate: dict, llm: ChatOllama) -> dict:
    """단일 후보를 revise. 항상 candidate를 mutate하지 않고 새 dict를 반환한다."""
    c = dict(candidate)
    prior = c.get("revise_attempts", 0) or 0
    attempt_no = prior + 1
    history_entry: dict = {
        "attempt": attempt_no,
        "issues_in": list(c.get("judge_issues") or []),
    }

    try:
        draft = _revise_draft(c, llm, attempt_no)
        ref_code, test_inputs = _reauthor_solution(
            {**c,
             "title": draft.get("title", c.get("title", "")),
             "statement": draft.get("statement", c.get("statement", "")),
             "intent_rubric": draft.get("intent_rubric", c.get("intent_rubric", {}))},
            llm,
        )
        if not ref_code:
            raise ValueError("author_solution 재호출이 빈 reference_code를 반환")

        # 수정 적용 + 다운스트림 게이트 리셋(verify가 test_cases를 다시 채우고 judge가 재평가).
        c["title"] = draft.get("title", c.get("title", ""))
        c["statement"] = draft.get("statement", c.get("statement", ""))
        c["intent_rubric"] = draft.get("intent_rubric", c.get("intent_rubric", {}))
        c["reference_code"] = ref_code
        c["test_inputs"] = test_inputs
        c["test_cases"] = []
        c["verify_passed"] = False
        c["verify_error"] = ""
        c["judge_passed"] = False
        history_entry["note"] = "revised"
    except Exception as exc:  # noqa: BLE001 — 본문 보존 + attempts만 증가시켜 루프 자연 종료
        log.warning("revise_one 실패 (candidate idx=%s, attempt=%d): %s",
                    c.get("index"), attempt_no, exc)
        history_entry["note"] = f"error: {type(exc).__name__}: {str(exc)[:160]}"

    c["revise_attempts"] = attempt_no
    history = list(c.get("revise_history") or [])
    history.append(history_entry)
    c["revise_history"] = history
    return c


def revise_problem(state: AuthoringState) -> dict:
    """judge_passed=False면서 보강 여유가 있는 후보만 표적 수정한다.

    대상 조건: verify_passed && !judge_passed && judge_issues 비어있지 않음 &&
    revise_attempts < REVISE_MAX_ATTEMPTS. JCQ_REVISE_ENABLED=0이면 라우터가
    진입을 막지만, 방어적으로 여기서도 no-op으로 폴백한다.
    """
    if not REVISE_ENABLED:
        return {"candidates": list(state["candidates"])}

    llm = make_chat_model(
        AUTHOR_MODEL,
        temperature=AUTHOR_RETRY_TEMPERATURE,
        json_mode=True,
        num_ctx=AUTHOR_NUM_CTX,
    )

    updated: list[dict] = []
    for c in state["candidates"]:
        eligible = (
            bool(c.get("verify_passed"))
            and not c.get("judge_passed")
            and bool(c.get("judge_issues"))
            and (c.get("revise_attempts", 0) or 0) < REVISE_MAX_ATTEMPTS
        )
        if eligible:
            updated.append(_revise_one(c, llm))
        else:
            updated.append(dict(c))
    return {"candidates": updated}
