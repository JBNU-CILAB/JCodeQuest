"""LangGraph stream 청크 → RunsView용 노드 상태 스냅샷 변환.

`graph.stream(...)`는 노드 완료마다 `{node_key: state_delta}`를 흘린다. state_delta는
그 노드가 반환한 dict(대부분 갱신된 `candidates` 리스트 포함). 여기선 그 delta에서
후보 단위 통과/탈락(candidate_results)과 in/out 카운트를 뽑아 admin 그래프가 바로 쓸
형태로 요약한다. 토큰/정밀 latency는 스트림 청크에 없으므로 LangSmith가 정밀치를 가진다.
"""
from __future__ import annotations

from typing import Any

# graph.py의 실제 노드 순서 (9개). RunsView NODE_DEFS와 1:1 대응.
NODE_ORDER: list[str] = [
    "fetch_problem",
    "retrieve_exemplars",
    "generate_variants",
    "verify_candidates",
    "judge_candidates",
    "solve_candidates",
    "attack_candidates",
    "compare_to_original",
    "persist_approved",
]

# 노드 종류 — 아이콘/색 매핑용. llm(LLM 호출) · sandbox(코드 실행) · db(DB·임베딩 I/O).
NODE_KIND: dict[str, str] = {
    "fetch_problem": "db",
    "retrieve_exemplars": "db",
    "generate_variants": "llm",
    "verify_candidates": "sandbox",
    "judge_candidates": "llm",
    "solve_candidates": "llm",
    "attack_candidates": "llm",
    "compare_to_original": "llm",
    "persist_approved": "db",
}


def _cand_idx(c: dict, fallback: int) -> int:
    v = c.get("index")
    return v if isinstance(v, int) else fallback


def _max_extra(cands: list[dict], key: str) -> int:
    """후보별 시도 횟수에서 '재시도' 수(=attempts-1)의 최댓값. 노드 retries 근사."""
    best = 0
    for c in cands:
        a = c.get(key)
        if isinstance(a, int) and a - 1 > best:
            best = a - 1
    return best


def summarize_node(node_key: str, delta: dict[str, Any]) -> dict[str, Any]:
    """한 노드의 delta를 {candidate_results, candidates_in, candidates_out, retries,
    outputs_preview} 부분 스냅샷으로. status/duration은 호출측(타이밍 보유)이 채운다."""
    out: dict[str, Any] = {
        "candidate_results": [],
        "retries": 0,
        "outputs_preview": None,
    }
    if not isinstance(delta, dict):
        return out

    cands = delta.get("candidates")
    cands = cands if isinstance(cands, list) else []

    if node_key == "fetch_problem":
        seeds = delta.get("seeds") or []
        sibs = delta.get("sibling_embeddings") or []
        out["outputs_preview"] = {"seeds": len(seeds), "siblings": len(sibs)}
        return out

    if node_key == "retrieve_exemplars":
        ex = delta.get("exemplars") or []
        out["outputs_preview"] = {
            "exemplars": [e.get("id") for e in ex if isinstance(e, dict)]
        }
        return out

    if node_key == "generate_variants":
        results = []
        for i, c in enumerate(cands):
            passed = c.get("novelty_passed", True)
            results.append({
                "idx": _cand_idx(c, i),
                "status": "pass" if passed else "warn",
                "note": (c.get("title") or "")[:48],
            })
        out["candidate_results"] = results
        out["candidates_out"] = len(cands)
        out["retries"] = _max_extra(cands, "novelty_attempts")
        return out

    if node_key == "verify_candidates":
        results = []
        for i, c in enumerate(cands):
            passed = bool(c.get("verify_passed"))
            results.append({
                "idx": _cand_idx(c, i),
                "status": "pass" if passed else "fail",
                "note": (c.get("verify_error") or "ok")[:60],
            })
        out["candidate_results"] = results
        out["candidates_in"] = len(cands)
        out["candidates_out"] = sum(1 for c in cands if c.get("verify_passed"))
        out["retries"] = _max_extra(cands, "verify_attempts")
        return out

    if node_key == "judge_candidates":
        results = []
        for i, c in enumerate(cands):
            passed = bool(c.get("judge_passed"))
            score = c.get("judge_score")
            note = f"score {score:.2f}" if isinstance(score, (int, float)) else "—"
            results.append({"idx": _cand_idx(c, i), "status": "pass" if passed else "fail", "note": note})
        out["candidate_results"] = results
        out["candidates_in"] = len(cands)
        out["candidates_out"] = sum(1 for c in cands if c.get("judge_passed"))
        return out

    if node_key == "solve_candidates":
        results = []
        for i, c in enumerate(cands):
            passed = bool(c.get("solver_passed"))
            results.append({
                "idx": _cand_idx(c, i),
                "status": "pass" if passed else "fail",
                "note": "solvable" if passed else "unsolved",
            })
        out["candidate_results"] = results
        out["candidates_in"] = len(cands)
        out["candidates_out"] = sum(1 for c in cands if c.get("solver_passed"))
        return out

    if node_key == "attack_candidates":
        results = []
        for i, c in enumerate(cands):
            # solver_passed 후보만 공격받음 — 미공격은 회색(skip 의미로 warn 회피)
            if not c.get("solver_passed"):
                continue
            passed = bool(c.get("discrimination_passed"))
            score = c.get("discrimination_score")
            note = f"discrim {score:.2f}" if isinstance(score, (int, float)) else "—"
            results.append({"idx": _cand_idx(c, i), "status": "pass" if passed else "warn", "note": note})
        out["candidate_results"] = results
        out["candidates_in"] = sum(1 for c in cands if c.get("solver_passed"))
        out["candidates_out"] = sum(
            1 for c in cands if c.get("solver_passed") and c.get("discrimination_passed", True)
        )
        return out

    if node_key == "compare_to_original":
        results = []
        for i, c in enumerate(cands):
            if not c.get("solver_passed"):
                continue
            passed = bool(c.get("compare_passed", True))
            hall = c.get("comparison_hallucination")
            note = f"hall {hall:.2f}" if isinstance(hall, (int, float)) else "—"
            results.append({"idx": _cand_idx(c, i), "status": "pass" if passed else "fail", "note": note})
        out["candidate_results"] = results
        return out

    if node_key == "persist_approved":
        saved = delta.get("saved_problem_ids") or []
        results = []
        for i, c in enumerate(cands):
            sid = c.get("saved_id")
            results.append({
                "idx": _cand_idx(c, i),
                "status": "pass" if sid else "fail",
                "note": f"saved #{sid}" if sid else "discarded",
            })
        out["candidate_results"] = results
        out["candidates_in"] = len(cands)
        out["candidates_out"] = len(saved)
        out["outputs_preview"] = {"saved_problem_ids": saved}
        return out

    return out
