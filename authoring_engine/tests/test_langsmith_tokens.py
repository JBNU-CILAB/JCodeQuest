"""langsmith_tokens.aggregate_node_tokens — 트레이스 span → 노드별 토큰 합산.

핵심: 노드 span 서브트리의 run_type=="llm" 리프만 합산(부모 집계값 중복 방지),
재시도로 같은 노드가 여러 번 나타나면 합산, llm 없는 노드는 제외.
"""
from __future__ import annotations

from authoring.langsmith_tokens import aggregate_node_tokens


def _span(id, name=None, parent=None, run_type="chain", prompt=None, completion=None, total=None):
    return {"id": id, "parent_run_id": parent, "name": name, "run_type": run_type,
            "prompt": prompt, "completion": completion, "total": total}


def test_sums_llm_leaves_ignores_parent_aggregate():
    spans = [
        _span("root", name="authoring_pipeline"),
        _span("g", name="generate_variants", parent="root", total=99999),  # 집계값 — 무시돼야
        _span("l1", parent="g", run_type="llm", prompt=100, completion=50, total=150),
        _span("l2", parent="g", run_type="llm", prompt=200, completion=80, total=280),
        _span("f", name="fetch_problem", parent="root"),  # llm 없음 → 제외
    ]
    out = aggregate_node_tokens(spans)
    assert out["generate_variants"] == {"prompt": 300, "completion": 130, "total": 430}
    assert "fetch_problem" not in out  # 토큰 0인 노드는 빠진다


def test_retry_same_node_summed():
    spans = [
        _span("g1", name="judge_candidates"),
        _span("l1", parent="g1", run_type="llm", prompt=10, completion=5, total=15),
        _span("g2", name="judge_candidates"),  # 재시도 — 같은 이름 두 번째 span
        _span("l2", parent="g2", run_type="llm", prompt=20, completion=10, total=30),
    ]
    out = aggregate_node_tokens(spans)
    assert out["judge_candidates"]["total"] == 45


def test_total_falls_back_to_prompt_plus_completion():
    spans = [
        _span("s", name="solve_candidates"),
        _span("l", parent="s", run_type="llm", prompt=40, completion=60, total=None),
    ]
    out = aggregate_node_tokens(spans)
    assert out["solve_candidates"]["total"] == 100


def test_deeply_nested_llm_counted():
    # 노드 → 중간 chain → llm (서브트리 DFS가 깊이와 무관하게 잡아야)
    spans = [
        _span("c", name="compare_to_original"),
        _span("mid", parent="c", run_type="chain"),
        _span("l", parent="mid", run_type="llm", prompt=7, completion=3, total=10),
    ]
    out = aggregate_node_tokens(spans)
    assert out["compare_to_original"]["total"] == 10


def test_empty_and_no_node_spans():
    assert aggregate_node_tokens([]) == {}
    # 노드 이름 매칭 없는 span만 있으면 빈 dict
    assert aggregate_node_tokens([_span("x", name="unknown", run_type="llm", total=5)]) == {}
