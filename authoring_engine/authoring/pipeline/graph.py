from langgraph.graph import END, StateGraph

from ..config import (
    REVISE_ENABLED,
    REVISE_MAX_ATTEMPTS,
    STRENGTHEN_ENABLED,
    STRENGTHEN_MAX_ATTEMPTS,
)
from ..schemas import AuthoringState
from .nodes.attack import attack_candidates
from .nodes.compare import compare_to_original
from .nodes.fetch import fetch_problem
from .nodes.generate import generate_variants
from .nodes.judge import judge_candidates
from .nodes.persist import persist_approved
from .nodes.retrieve import retrieve_exemplars
from .nodes.revise import revise_problem
from .nodes.solver import solve_candidates
from .nodes.strengthen import strengthen_tests
from .nodes.verify import verify_candidates


# ── short-circuit 라우터 — 살아있는 후보가 0이면 하위 노드를 건너뛰고 종료 ──────
# 선형 체인이라 후보가 전멸해도 하위가 무의미하게 실행되던 것을 막는다(토큰 절약 +
# RunsView 상태 정확도). 각 게이트의 '다음 단계가 실제로 처리할 후보' 기준으로 판정.
def _route_after_generate(state: AuthoringState) -> str:
    # 생성된 후보 자체가 없으면 더 진행할 게 없다.
    return "continue" if state.get("candidates") else "end"


def _route_after_judge(state: AuthoringState) -> str:
    """판사 통과·실패·revise 여유를 종합해 다음 단계 선택.

    우선순위:
      1. 살아있는(verify_passed) 후보가 0이면 → END.
      2. judge 실패자 중 revise 여유가 남아 있으면 → revise_problem (먼저 살리기 시도).
      3. judge 통과자가 하나라도 있으면 → solve_candidates 진행.
      4. 그도 없으면 → END.

    실패자 우선 보강이 통과자의 진행을 최대 REVISE_MAX_ATTEMPTS회만큼 지연시키지만
    변형 수율을 최대화한다. 무한루프는 revise 노드가 revise_attempts를 매번 1씩
    증가시키므로 모든 실패자가 MAX에 도달하면 (3)으로 자연 탈출한다.
    """
    cands = state.get("candidates", [])
    if not any(c.get("verify_passed") for c in cands):
        return "end"
    if REVISE_ENABLED and any(
        c.get("verify_passed")
        and not c.get("judge_passed")
        and bool(c.get("judge_issues"))
        and (c.get("revise_attempts", 0) or 0) < REVISE_MAX_ATTEMPTS
        for c in cands
    ):
        return "revise"
    if any(c.get("judge_passed") for c in cands):
        return "continue"
    return "end"


def _route_after_solve(state: AuthoringState) -> str:
    # attack/compare/persist는 solver_passed를 키로 동작 → 풀이 가능 후보 0이면 종료.
    return "continue" if any(c.get("solver_passed") for c in state.get("candidates", [])) else "end"


# ── attack 후 분기 — 변별력 보강 루프 vs 진행 ──────────────────────────────────
def _route_after_attack(state: AuthoringState) -> str:
    """변별력 미달이면서 보강 시도 여유가 있는 후보가 있으면 strengthen_tests로 루프백,
    아니면 compare_to_original로 진행. 살아있는(solver_passed) 후보가 0이면 종료.

    무한루프 방지: STRENGTHEN_ENABLED 가드 + strengthen_tests가 매 진입마다
    strengthen_attempts를 1씩 올리므로, 모든 미통과 후보가 MAX에 도달하면 'continue'로 빠진다.
    """
    survivors = [c for c in state.get("candidates", []) if c.get("solver_passed")]
    if not survivors:
        return "end"
    if STRENGTHEN_ENABLED and any(
        not c.get("discrimination_passed", True)
        and c.get("strengthen_attempts", 0) < STRENGTHEN_MAX_ATTEMPTS
        for c in survivors
    ):
        return "strengthen"
    return "continue"


def build_graph():
    """출제 파이프라인 LangGraph를 빌드해 반환한다.

    노드 순서:
      fetch_problem → retrieve_exemplars → generate_variants → verify_candidates
        → judge_candidates ⇄ revise_problem (품질 보강 루프, verify로 루프백)
        → solve_candidates → attack_candidates
        ⇄ strengthen_tests (변별력 보강 루프) → compare_to_original → persist_approved

    revise_problem은 judge_passed=False 후보의 statement·rubric을 판사 issues로 표적
    수정하고 author_solution을 재호출한 뒤 verify_candidates로 루프백한다(verify와 judge
    노드에 'judge_passed면 스킵' 가드가 있어 통과 후보는 재처리되지 않음). 매 진입마다
    revise_attempts를 1 증가시켜 REVISE_MAX_ATTEMPTS에서 루프가 끝난다.

    retrieve_exemplars는 같은 카테고리 모범 사례를 MMR로 골라 generate에 grounding
    자료로 넘긴다(RAG). fetch가 적재한 형제 임베딩을 재사용하므로 fetch 직후에 둔다.

    attack_candidates는 solver_passed 후보에 결함 풀이를 던져 테스트 변별력을
    검사하는 게이트다. 풀 수 있는(solve) 후보에만 의미가 있으므로 solve 뒤에 둔다.

    strengthen_tests는 변별력 미달 후보의 약점을 '걸러내는' 판별 테스트를 추가한 뒤
    attack_candidates로 되돌아가 강화된 테스트셋으로 재검증하는 루프다(_route_after_attack).
    보강마다 strengthen_attempts가 올라 STRENGTHEN_MAX_ATTEMPTS에서 루프가 끝난다.

    compare_to_original은 단일 judge가 원본과 변형을 비교해 3축 수치를 기록하고
    환각·의도유사도를 보조 게이트로 적용한다. 루프가 끝난(또는 보강 비활성) 후보에만
    적용되므로 attack_candidates 뒤, persist_approved 직전에 위치한다.
    """
    g: StateGraph = StateGraph(AuthoringState)

    g.add_node("fetch_problem", fetch_problem)
    g.add_node("retrieve_exemplars", retrieve_exemplars)
    g.add_node("generate_variants", generate_variants)
    g.add_node("verify_candidates", verify_candidates)
    g.add_node("judge_candidates", judge_candidates)
    g.add_node("revise_problem", revise_problem)
    g.add_node("solve_candidates", solve_candidates)
    g.add_node("attack_candidates", attack_candidates)
    g.add_node("strengthen_tests", strengthen_tests)
    g.add_node("compare_to_original", compare_to_original)
    g.add_node("persist_approved", persist_approved)

    g.set_entry_point("fetch_problem")
    g.add_edge("fetch_problem", "retrieve_exemplars")
    g.add_edge("retrieve_exemplars", "generate_variants")
    # 후보 전멸 지점마다 END로 short-circuit (generate/judge/solve 후)
    g.add_conditional_edges(
        "generate_variants", _route_after_generate,
        {"continue": "verify_candidates", "end": END},
    )
    g.add_edge("verify_candidates", "judge_candidates")
    # judge 실패자가 revise 여유 있으면 revise → verify로 루프백, 통과자 있으면 solve로,
    # 둘 다 아니면 END. revise_problem이 verify_passed/judge_passed를 리셋하므로
    # 재진입 시 verify/judge 가드가 revise된 후보만 다시 처리한다.
    g.add_conditional_edges(
        "judge_candidates", _route_after_judge,
        {"revise": "revise_problem", "continue": "solve_candidates", "end": END},
    )
    g.add_edge("revise_problem", "verify_candidates")
    g.add_conditional_edges(
        "solve_candidates", _route_after_solve,
        {"continue": "attack_candidates", "end": END},
    )
    # 변별력 미달 + 보강 여유 → strengthen_tests로 루프백, 아니면 compare로 진행.
    g.add_conditional_edges(
        "attack_candidates", _route_after_attack,
        {"strengthen": "strengthen_tests", "continue": "compare_to_original", "end": END},
    )
    g.add_edge("strengthen_tests", "attack_candidates")
    g.add_edge("compare_to_original", "persist_approved")
    g.add_edge("persist_approved", END)

    return g.compile()
