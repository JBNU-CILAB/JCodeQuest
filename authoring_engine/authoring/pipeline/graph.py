from langgraph.graph import END, StateGraph

from ..schemas import AuthoringState
from .nodes.attack import attack_candidates
from .nodes.compare import compare_to_original
from .nodes.fetch import fetch_problem
from .nodes.generate import generate_variants
from .nodes.judge import judge_candidates
from .nodes.persist import persist_approved
from .nodes.retrieve import retrieve_exemplars
from .nodes.solver import solve_candidates
from .nodes.verify import verify_candidates


def build_graph():
    """출제 파이프라인 LangGraph를 빌드해 반환한다.

    노드 순서:
      fetch_problem → retrieve_exemplars → generate_variants → verify_candidates
        → judge_candidates → solve_candidates → attack_candidates
        → compare_to_original → persist_approved

    retrieve_exemplars는 같은 카테고리 모범 사례를 MMR로 골라 generate에 grounding
    자료로 넘긴다(RAG). fetch가 적재한 형제 임베딩을 재사용하므로 fetch 직후에 둔다.

    attack_candidates는 solver_passed 후보에 결함 풀이를 던져 테스트 변별력을
    검사하는 게이트다. 풀 수 있는(solve) 후보에만 의미가 있으므로 solve 뒤에 둔다.

    compare_to_original은 단일 judge가 원본과 변형을 비교해 3축 수치를 기록하고
    환각·의도유사도를 보조 게이트로 적용한다. 직전 단계가 모두 끝난 후보에만
    적용되므로 attack_candidates 뒤, persist_approved 직전에 위치한다.
    """
    g: StateGraph = StateGraph(AuthoringState)

    g.add_node("fetch_problem", fetch_problem)
    g.add_node("retrieve_exemplars", retrieve_exemplars)
    g.add_node("generate_variants", generate_variants)
    g.add_node("verify_candidates", verify_candidates)
    g.add_node("judge_candidates", judge_candidates)
    g.add_node("solve_candidates", solve_candidates)
    g.add_node("attack_candidates", attack_candidates)
    g.add_node("compare_to_original", compare_to_original)
    g.add_node("persist_approved", persist_approved)

    g.set_entry_point("fetch_problem")
    g.add_edge("fetch_problem", "retrieve_exemplars")
    g.add_edge("retrieve_exemplars", "generate_variants")
    g.add_edge("generate_variants", "verify_candidates")
    g.add_edge("verify_candidates", "judge_candidates")
    g.add_edge("judge_candidates", "solve_candidates")
    g.add_edge("solve_candidates", "attack_candidates")
    g.add_edge("attack_candidates", "compare_to_original")
    g.add_edge("compare_to_original", "persist_approved")
    g.add_edge("persist_approved", END)

    return g.compile()
