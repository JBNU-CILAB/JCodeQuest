"""node_stats.summarize_node — LangGraph delta → RunsView 노드 스냅샷 변환.

각 노드가 후보 단위 통과/탈락(candidate_results)과 in/out 카운트를 올바로 뽑는지.
"""
from __future__ import annotations

from authoring.pipeline.node_stats import NODE_KIND, NODE_ORDER, summarize_node


def test_node_order_and_kinds_cover_graph():
    assert NODE_ORDER[0] == "fetch_problem"
    assert NODE_ORDER[-1] == "persist_approved"
    assert len(NODE_ORDER) == 11  # revise_problem 추가됨 (judge ⇄ revise 품질 보강 루프)
    assert set(NODE_KIND) == set(NODE_ORDER)
    assert NODE_KIND["generate_variants"] == "llm"
    assert NODE_KIND["verify_candidates"] == "sandbox"
    assert NODE_KIND["persist_approved"] == "db"
    # strengthen_tests는 attack 직후에 위치한 변별력 보강 루프 노드.
    assert NODE_ORDER[NODE_ORDER.index("attack_candidates") + 1] == "strengthen_tests"
    assert NODE_KIND["strengthen_tests"] == "llm"
    # revise_problem은 judge 직후에 위치한 품질 보강 루프 노드(verify로 루프백).
    assert NODE_ORDER[NODE_ORDER.index("judge_candidates") + 1] == "revise_problem"
    assert NODE_KIND["revise_problem"] == "llm"


def test_fetch_and_retrieve_outputs_preview():
    f = summarize_node("fetch_problem", {"seeds": [1, 2], "sibling_embeddings": [1]})
    assert f["outputs_preview"] == {"seeds": 2, "siblings": 1}
    r = summarize_node("retrieve_exemplars", {"exemplars": [{"id": 7}, {"id": 9}]})
    assert r["outputs_preview"] == {"exemplars": [7, 9]}
    # 후보 단위 결과는 없음
    assert f["candidate_results"] == [] and r["candidate_results"] == []


def test_verify_pass_fail_and_retries():
    delta = {
        "candidates": [
            {"index": 0, "verify_passed": True, "verify_attempts": 1},
            {"index": 1, "verify_passed": False, "verify_error": "RE: boom", "verify_attempts": 3},
        ]
    }
    s = summarize_node("verify_candidates", delta)
    assert s["candidates_in"] == 2
    assert s["candidates_out"] == 1
    assert s["retries"] == 2  # max(attempts-1)
    assert s["candidate_results"][0]["status"] == "pass"
    assert s["candidate_results"][1]["status"] == "fail"
    assert "boom" in s["candidate_results"][1]["note"]


def test_judge_note_has_score():
    s = summarize_node(
        "judge_candidates",
        {"candidates": [{"index": 0, "judge_passed": True, "judge_score": 0.83}]},
    )
    assert s["candidate_results"][0]["status"] == "pass"
    assert "0.83" in s["candidate_results"][0]["note"]
    assert s["candidates_out"] == 1


def test_attack_only_counts_solvable():
    delta = {
        "candidates": [
            {"index": 0, "solver_passed": True, "discrimination_passed": True, "discrimination_score": 1.0},
            {"index": 1, "solver_passed": True, "discrimination_passed": False, "discrimination_score": 0.0},
            {"index": 2, "solver_passed": False},  # 미공격 — 결과에서 제외
        ]
    }
    s = summarize_node("attack_candidates", delta)
    assert len(s["candidate_results"]) == 2
    assert s["candidates_in"] == 2
    assert s["candidates_out"] == 1
    assert {r["status"] for r in s["candidate_results"]} == {"pass", "warn"}


def test_strengthen_node_stats():
    delta = {
        "candidates": [
            {"index": 0, "strengthen_added": 2, "strengthen_attempts": 1},
            {"index": 1, "strengthen_added": 0, "strengthen_attempts": 2},
            {"index": 2},  # 보강 대상 아님(strengthen_added 없음) — 결과에서 제외
        ]
    }
    s = summarize_node("strengthen_tests", delta)
    assert len(s["candidate_results"]) == 2
    assert s["candidates_in"] == 2
    assert s["candidates_out"] == 1  # added>0 인 후보만
    assert {r["status"] for r in s["candidate_results"]} == {"pass", "warn"}
    assert s["retries"] == 1  # max(attempts-1) = max(0,1)


def test_revise_node_stats():
    delta = {
        "candidates": [
            {"index": 0, "revise_attempts": 1, "revise_history": [{"note": "revised"}]},
            {"index": 1, "revise_attempts": 2, "revise_history": [
                {"note": "revised"}, {"note": "error: RuntimeError: x"},
            ]},
            {"index": 2},  # revise 대상 아님(attempts 없음) — 결과에서 제외
        ]
    }
    s = summarize_node("revise_problem", delta)
    assert len(s["candidate_results"]) == 2
    assert s["candidates_in"] == 2
    assert s["candidates_out"] == 1  # 마지막 note가 "revised"인 후보만
    statuses = {r["status"] for r in s["candidate_results"]}
    assert statuses == {"pass", "warn"}
    assert s["retries"] == 1  # max(attempts-1) = max(0,1) = 1


def test_persist_saved_ids():
    delta = {
        "candidates": [
            {"index": 0, "saved_id": 101},
            {"index": 1, "saved_id": None},
        ],
        "saved_problem_ids": [101],
    }
    s = summarize_node("persist_approved", delta)
    assert s["candidates_out"] == 1
    assert s["outputs_preview"] == {"saved_problem_ids": [101]}
    assert s["candidate_results"][0]["note"] == "saved #101"
    assert s["candidate_results"][1]["status"] == "fail"


def test_robust_to_missing_candidates():
    # delta가 dict가 아니거나 candidates 없을 때도 안전
    assert summarize_node("judge_candidates", {})["candidate_results"] == []
    assert summarize_node("generate_variants", {"candidates": []})["candidates_out"] == 0
