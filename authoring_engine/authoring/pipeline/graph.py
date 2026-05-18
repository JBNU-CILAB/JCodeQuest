from langgraph.graph import END, StateGraph

from ..schemas import AuthoringState
from .nodes.compare import compare_to_original
from .nodes.fetch import fetch_problem
from .nodes.generate import generate_variants
from .nodes.judge import judge_candidates
from .nodes.persist import persist_approved
from .nodes.solver import solve_candidates
from .nodes.verify import verify_candidates


def build_graph():
    """출제 파이프라인 LangGraph를 빌드해 반환한다.

    노드 순서:
      fetch_problem → generate_variants → verify_candidates
        → judge_candidates → solve_candidates → compare_to_original
        → persist_approved

    compare_to_original은 단일 judge가 원본과 변형을 비교해 3축 수치를
    기록하는 단계(게이트 아님). 직전 3-judge 단계가 모두 끝난 후보에만
    적용되므로 solve_candidates 뒤, persist_approved 직전에 위치한다.
    """
    g: StateGraph = StateGraph(AuthoringState)

    g.add_node("fetch_problem", fetch_problem)
    g.add_node("generate_variants", generate_variants)
    g.add_node("verify_candidates", verify_candidates)
    g.add_node("judge_candidates", judge_candidates)
    g.add_node("solve_candidates", solve_candidates)
    g.add_node("compare_to_original", compare_to_original)
    g.add_node("persist_approved", persist_approved)

    g.set_entry_point("fetch_problem")
    g.add_edge("fetch_problem", "generate_variants")
    g.add_edge("generate_variants", "verify_candidates")
    g.add_edge("verify_candidates", "judge_candidates")
    g.add_edge("judge_candidates", "solve_candidates")
    g.add_edge("solve_candidates", "compare_to_original")
    g.add_edge("compare_to_original", "persist_approved")
    g.add_edge("persist_approved", END)

    return g.compile()
