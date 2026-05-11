import json

from jcq_shared.schemas import IntentRubric
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from ...config import AUTHOR_MODEL, OLLAMA_BASE_URL, VARIANT_COUNT
from ...schemas import AuthoringState, CandidateProblem
from ..prompts import DRAFT_SYSTEM, DRAFT_USER, SOLUTION_SYSTEM, SOLUTION_USER


def _clean_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return json.loads(text.strip())


def _seed_fields(seeds: list[dict], idx: int) -> tuple[str, str, str]:
    if idx < len(seeds):
        s = seeds[idx]
        r = s.get("intent_rubric", {})
        return (
            s.get("title", "N/A"),
            r.get("one_line_summary", "N/A"),
            r.get("expected_approach", "N/A"),
        )
    return "N/A", "N/A", "N/A"


def generate_variants(state: AuthoringState) -> dict:
    """각 변형마다 draft_problem → author_solution 두 단계를 순차 호출한다."""
    original = state["original_problem"]
    seeds = state.get("seeds", [])
    count = state.get("target_count", VARIANT_COUNT)

    # 원본을 첫 번째 seed로 포함해 다양성 신호를 풍부하게 만든다
    all_seeds = [original, *seeds]

    llm = ChatOllama(
        model=AUTHOR_MODEL,
        temperature=0,
        format="json",
        base_url=OLLAMA_BASE_URL,
        num_ctx=8192,
        keep_alive="30m",
    )

    candidates: list[CandidateProblem] = []
    errors: list[str] = list(state.get("errors", []))

    for i in range(count):
        # 각 변형마다 seed 순서를 rotate해서 다양성 확보
        rotated = all_seeds[i % len(all_seeds) :] + all_seeds[: i % len(all_seeds)]
        s1, s2, s3 = (
            _seed_fields(rotated, 0),
            _seed_fields(rotated, 1),
            _seed_fields(rotated, 2),
        )

        # ── step 1: draft_problem ──────────────────────────────────────────
        try:
            draft_resp = llm.invoke(
                [
                    SystemMessage(content=DRAFT_SYSTEM),
                    HumanMessage(
                        content=DRAFT_USER.format(
                            category=original["category"],
                            level=original["level"],
                            time_limit_ms=original["time_limit_ms"],
                            memory_limit_mb=original["memory_limit_mb"],
                            variant_index=i + 1,
                            seed_1_title=s1[0],
                            seed_1_summary=s1[1],
                            seed_1_approach=s1[2],
                            seed_2_title=s2[0],
                            seed_2_summary=s2[1],
                            seed_2_approach=s2[2],
                            seed_3_title=s3[0],
                            seed_3_summary=s3[1],
                            seed_3_approach=s3[2],
                        )
                    ),
                ]
            )
            draft = _clean_json(draft_resp.content)
        except Exception as exc:
            errors.append(f"variant {i}: draft_problem 실패 — {exc}")
            continue

        rubric = draft.get("intent_rubric", {})
        try:
            IntentRubric.model_validate(rubric)
        except Exception as exc:
            errors.append(f"variant {i}: intent_rubric 검증 실패 — {exc}")
            continue

        # ── step 2: author_solution ────────────────────────────────────────
        try:
            sol_resp = llm.invoke(
                [
                    SystemMessage(content=SOLUTION_SYSTEM),
                    HumanMessage(
                        content=SOLUTION_USER.format(
                            title=draft.get("title", ""),
                            statement=draft.get("statement", ""),
                            expected_approach=rubric.get("expected_approach", ""),
                            key_insight=rubric.get("key_insight", ""),
                            expected_complexity=rubric.get("expected_complexity", ""),
                            must_handle=", ".join(rubric.get("must_handle", [])),
                            forbidden_patterns=", ".join(
                                rubric.get("forbidden_patterns", [])
                            ),
                            time_limit_ms=original["time_limit_ms"],
                            memory_limit_mb=original["memory_limit_mb"],
                        )
                    ),
                ]
            )
            solution = _clean_json(sol_resp.content)
        except Exception as exc:
            errors.append(f"variant {i}: author_solution 실패 — {exc}")
            continue

        candidate: CandidateProblem = {
            "index": i,
            "category": original["category"],
            "level": original["level"],
            "points": original["points"],
            "time_limit_ms": original["time_limit_ms"],
            "memory_limit_mb": original["memory_limit_mb"],
            "title": draft.get("title", ""),
            "statement": draft.get("statement", ""),
            "intent_rubric": rubric,
            "reference_code": solution.get("reference_code", ""),
            "test_inputs": solution.get("test_inputs", []),
            "test_cases": [],
            "verify_passed": False,
            "verify_error": "",
            "verify_attempts": 0,
            "judge_passed": False,
            "judge_score": 0.0,
            "judge_rationale": "",
            "judge_issues": [],
            "solver_results": [],
            "solver_passed": False,
            "saved_id": None,
        }
        candidates.append(candidate)

    return {"candidates": candidates, "errors": errors}
