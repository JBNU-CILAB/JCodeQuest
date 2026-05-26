import json
import logging

from jcq_shared.schemas import IntentRubric
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from ...config import (
    AUTHOR_MODEL,
    AUTHOR_NUM_CTX,
    AUTHOR_TEMPERATURE,
    NOVELTY_ENABLED,
    NOVELTY_MAX_RETRIES,
    NOVELTY_THRESHOLD,
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    VARIANT_COUNT,
)
from ...embeddings import embed_text, max_similarity, problem_text
from ...llm import make_chat_model
from ...schemas import AuthoringState, CandidateProblem
from ..prompts import (
    DRAFT_SYSTEM,
    DRAFT_USER,
    EXEMPLAR_BLOCK_HEADER,
    EXEMPLAR_ITEM,
    SEED_BLOCK,
    SOLUTION_SYSTEM,
    SOLUTION_USER,
)

log = logging.getLogger(__name__)


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


def _exemplar_block(exemplars: list[dict]) -> str:
    """retrieve_exemplars가 고른 모범 사례를 draft 프롬프트용 rubric 블록으로 포맷.
    비어 있으면 ""(호출 측이 seed 폴백으로 전환)."""
    if not exemplars:
        return ""
    items = "\n".join(
        EXEMPLAR_ITEM.format(
            n=i + 1,
            title=ex.get("title", "N/A"),
            one_line_summary=ex.get("one_line_summary", "N/A"),
            expected_approach=ex.get("expected_approach", "N/A"),
            key_insight=ex.get("key_insight", "N/A"),
            expected_complexity=ex.get("expected_complexity", "N/A"),
        )
        for i, ex in enumerate(exemplars)
    )
    return f"{EXEMPLAR_BLOCK_HEADER}\n{items}"


def _seed_block(seed_fields: tuple[tuple[str, str, str], ...]) -> str:
    """exemplar가 없을 때의 폴백 — 기존 seed 기반 블록."""
    s1, s2, s3 = seed_fields
    return SEED_BLOCK.format(
        seed_1_title=s1[0], seed_1_summary=s1[1], seed_1_approach=s1[2],
        seed_2_title=s2[0], seed_2_summary=s2[1], seed_2_approach=s2[2],
        seed_3_title=s3[0], seed_3_summary=s3[1], seed_3_approach=s3[2],
    )


def _overlap_feedback(closest_title: str, score: float) -> str:
    """재draft 시 draft 프롬프트에 끼워 넣는 겹침 피드백. 어떤 기존 문제와 얼마나
    유사했는지 알려 LLM이 다른 방향으로 설계하도록 유도한다."""
    return (
        f"\n[NOVELTY] 직전 시도는 기존 문제 '{closest_title}'와 풀이 흐름이 너무 유사했다"
        f" (유사도 {score:.2f}). 같은 카테고리 안에서 입력 형태·부분문제 구성·풀이 절차가"
        f" 뚜렷이 다른 새 변형을 설계하라.\n"
    )


def _base_candidate(
    index: int, original: dict, draft: dict | None, rubric: dict | None
) -> CandidateProblem:
    """모든 CandidateProblem 키를 기본값으로 채운 후보. 성공/폐기 경로가 공통으로 쓴다."""
    return {  # type: ignore[return-value]
        "index": index,
        "category": original["category"],
        "level": original["level"],
        "points": original["points"],
        "time_limit_ms": original["time_limit_ms"],
        "memory_limit_mb": original["memory_limit_mb"],
        "title": (draft or {}).get("title", ""),
        "statement": (draft or {}).get("statement", ""),
        "intent_rubric": rubric or {},
        "reference_code": "",
        "test_inputs": [],
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
        "novelty_passed": True,
        "novelty_max_similarity": 0.0,
        "novelty_closest_id": None,
        "novelty_attempts": 0,
        "embedding": None,
        "saved_id": None,
    }


def _draft_variant(
    llm: ChatOllama,
    original: dict,
    reference_block: str,
    variant_index: int,
    novelty_feedback: str,
) -> tuple[dict, dict]:
    """draft_problem 1회 호출 → (draft, rubric). rubric 검증 실패 시 예외.

    reference_block은 retrieve_exemplars의 rubric 블록(RAG) 또는 seed 폴백 블록.
    """
    draft_resp = llm.invoke(
        [
            SystemMessage(content=DRAFT_SYSTEM),
            HumanMessage(
                content=DRAFT_USER.format(
                    category=original["category"],
                    level=original["level"],
                    time_limit_ms=original["time_limit_ms"],
                    memory_limit_mb=original["memory_limit_mb"],
                    variant_index=variant_index,
                    reference_block=reference_block,
                    novelty_feedback=novelty_feedback,
                )
            ),
        ]
    )
    draft = _clean_json(draft_resp.content)
    rubric = draft.get("intent_rubric", {})
    IntentRubric.model_validate(rubric)  # 검증 실패 시 호출 측이 잡는다
    return draft, rubric


def generate_variants(state: AuthoringState) -> dict:
    """각 변형마다 draft_problem → (신규성 검사 + 재draft 루프) → author_solution을 호출한다.

    신규성 검사는 draft만으로 가능하므로 비싼 author_solution 이전에 둔다. draft가 같은
    카테고리 형제(또는 이번 배치에서 이미 채택된 변형)와 임계값 이상으로 유사하면 겹침
    피드백을 주고 재draft하며, NOVELTY_MAX_RETRIES회까지 시도해도 신규성을 못 얻으면
    author_solution을 건너뛰고 후보를 폐기한다(novelty_passed=False). 임베딩 호출 실패는
    fail-open으로 흡수해 검사가 막혀도 파이프라인이 멈추지 않는다.
    """
    original = state["original_problem"]
    seeds = state.get("seeds", [])
    count = state.get("target_count", VARIANT_COUNT)

    # 원본을 첫 번째 seed로 포함해 다양성 신호를 풍부하게 만든다
    all_seeds = [original, *seeds]

    # RAG: retrieve_exemplars가 고른 모범 사례 블록. 있으면 모든 변형이 공유하고(안정적
    # grounding), 비어 있으면 변형별 rotate된 seed 폴백을 쓴다.
    exemplar_block = _exemplar_block(state.get("exemplars", []))

    # 신규성 검사 모집단: 카테고리 형제(저장 임베딩) + 이번 실행에서 채택된 변형(누적).
    # 후자를 더해 같은 배치 안의 변형끼리도 서로 구별되게 한다(배치 항목은 id=음수 sentinel).
    sibling_pop: list[tuple[int, str, list[float] | None]] = [
        (e.get("id"), e.get("title", ""), e.get("embedding"))
        for e in state.get("sibling_embeddings", [])
    ]
    batch_pop: list[tuple[int, str, list[float] | None]] = []

    llm = make_chat_model(
        AUTHOR_MODEL,
        temperature=AUTHOR_TEMPERATURE,
        json_mode=True,
        num_ctx=AUTHOR_NUM_CTX,
    )

    candidates: list[CandidateProblem] = []
    errors: list[str] = list(state.get("errors", []))

    for i in range(count):
        # exemplar가 있으면 그 블록을, 없으면 변형별 rotate된 seed 폴백 블록을 쓴다.
        if exemplar_block:
            reference_block = exemplar_block
        else:
            rotated = all_seeds[i % len(all_seeds) :] + all_seeds[: i % len(all_seeds)]
            reference_block = _seed_block(
                (
                    _seed_fields(rotated, 0),
                    _seed_fields(rotated, 1),
                    _seed_fields(rotated, 2),
                )
            )

        # ── step 1: draft_problem (+ 신규성 재생성 루프) ────────────────────
        draft: dict | None = None
        rubric: dict | None = None
        embedding: list[float] | None = None
        novelty_feedback = ""
        novelty_passed = True
        novelty_score = 0.0
        novelty_closest_id: int | None = None
        novelty_closest_title = ""
        attempts = 0
        draft_failed = False

        max_attempts = (NOVELTY_MAX_RETRIES + 1) if NOVELTY_ENABLED else 1
        for attempt in range(max_attempts):
            try:
                draft, rubric = _draft_variant(
                    llm, original, reference_block, i + 1, novelty_feedback
                )
            except Exception as exc:
                errors.append(f"variant {i}: draft_problem 실패 — {exc}")
                draft_failed = True
                break

            attempts = attempt + 1
            if not NOVELTY_ENABLED:
                break

            try:
                embedding = embed_text(
                    problem_text(
                        draft.get("title", ""), draft.get("statement", ""), rubric
                    )
                )
            except Exception as exc:  # noqa: BLE001 — fail-open
                log.warning("variant %d: 임베딩 실패 — 신규성 fail-open: %s", i, exc)
                embedding = None
                break

            novelty_score, novelty_closest_id, novelty_closest_title = max_similarity(
                embedding, sibling_pop + batch_pop
            )
            if novelty_score < NOVELTY_THRESHOLD:
                novelty_passed = True
                break
            # 너무 유사 → 겹침 피드백을 주고 재draft
            novelty_passed = False
            novelty_feedback = _overlap_feedback(novelty_closest_title, novelty_score)

        if draft_failed:
            continue

        # rubric 검증은 _draft_variant 안에서 끝났으므로 여기서 별도 검증 불필요

        if not novelty_passed:
            # 재시도 소진 — author_solution은 돌리지 않고 폐기 후보로 기록(추적/뷰어용)
            errors.append(
                f"variant {i}: 신규성 미달 — '{novelty_closest_title}'와 유사"
                f" (유사도 {novelty_score:.2f}), {attempts}회 시도 후 폐기"
            )
            cand = _base_candidate(i, original, draft, rubric)
            cand["novelty_passed"] = False
            cand["novelty_max_similarity"] = round(novelty_score, 3)
            cand["novelty_closest_id"] = novelty_closest_id
            cand["novelty_attempts"] = attempts
            candidates.append(cand)
            continue

        # ── step 2: author_solution ────────────────────────────────────────
        assert draft is not None and rubric is not None
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

        cand = _base_candidate(i, original, draft, rubric)
        cand["reference_code"] = solution.get("reference_code", "")
        cand["test_inputs"] = solution.get("test_inputs", [])
        cand["novelty_passed"] = True
        cand["novelty_max_similarity"] = round(novelty_score, 3)
        cand["novelty_closest_id"] = novelty_closest_id
        cand["novelty_attempts"] = attempts
        cand["embedding"] = embedding
        candidates.append(cand)

        # 채택된 변형을 배치 모집단에 추가 → 같은 실행 내 다른 변형과도 구별되게(id=음수 sentinel)
        if embedding is not None:
            batch_pop.append((-(i + 1), cand["title"], embedding))

    return {"candidates": candidates, "errors": errors}
