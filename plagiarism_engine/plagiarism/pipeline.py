"""표절 검토 LangGraph 파이프라인 (Phase 1 — Dolos 단독, LLM 없음).

  fetch_submissions → run_dolos → screen_pairs → persist_flags

Phase 2에서 screen_pairs 뒤에 adjudicate_pairs(멀티에이전트) 노드를 끼워 넣는다.
nodes는 authoring 컨벤션과 동일: def node(state) -> dict(부분 갱신).
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from langgraph.graph import END, StateGraph

from . import backend_client, config
from .dolos import run_dolos
from .schemas import PlagiarismState

log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 노드 ──────────────────────────────────────────────────────────────────
def fetch_submissions(state: PlagiarismState) -> dict:
    """문제의 AC 제출 적재. 같은 유저의 여러 AC는 최신 1건만 — self-pair 방지."""
    rows = backend_client.list_ac_submissions(state["problem_id"], config.INCLUDE_VERDICT)
    # created_at asc 정렬로 오므로, 유저별로 마지막(=최신)이 남게 덮어쓴다.
    by_user: dict[int, dict] = {}
    for r in rows:
        by_user[r["user_id"]] = {
            "submission_id": r["submission_id"],
            "user_id": r["user_id"],
            "code": (r.get("code") or "")[: config.MAX_CODE_BYTES],
        }
    # 의미 검토 에이전트(Phase 2)용 '문제 의도' 컨텍스트 — 비싸지 않게 한 번만.
    problem_ctx = ""
    if config.ENSEMBLE_ENABLED:
        prob = backend_client.fetch_problem(state["problem_id"]) or {}
        rubric = prob.get("intent_rubric") or {}
        if isinstance(rubric, dict):
            problem_ctx = str(rubric.get("expected_approach") or rubric.get("one_line_summary") or "")[:600]
    return {"submissions": list(by_user.values()), "problem_ctx": problem_ctx}


def adjudicate_pairs(state: PlagiarismState) -> dict:
    """의심 쌍을 역할 분화 멀티에이전트로 판정(상위 N개). 결과를 suspect_pairs에 병합."""
    from .agents import adjudicate_pair

    suspect = list(state.get("suspect_pairs") or [])
    subs = {str(s["submission_id"]): s for s in (state.get("submissions") or [])}
    ctx = state.get("problem_ctx") or ""
    for i, p in enumerate(suspect[: config.ADJUDICATE_TOP_N]):
        a = subs.get(str(p.get("a_id")))
        b = subs.get(str(p.get("b_id")))
        if not a or not b:
            continue
        suspect[i] = {**p, **adjudicate_pair(p, a["code"], b["code"], ctx)}
    return {"suspect_pairs": suspect}


def run_dolos_node(state: PlagiarismState) -> dict:
    subs = state.get("submissions") or []
    files = [{"id": str(s["submission_id"]), "content": s["code"]} for s in subs]
    if config.ENGINE == "winnow":
        from .winnow import winnow_pairs
        return {"dolos_pairs": winnow_pairs(files), "engine": "winnow"}
    try:
        return {"dolos_pairs": run_dolos(files, language=config.LANGUAGE), "engine": "dolos"}
    except Exception as exc:  # noqa: BLE001
        if config.ENGINE == "dolos":
            raise  # 강제 Dolos인데 실패 → run을 failed로(조용한 폴백 금지)
        log.warning("Dolos 실패 → winnow 폴백: %s", exc)
        from .winnow import winnow_pairs
        return {"dolos_pairs": winnow_pairs(files), "engine": "winnow"}


def screen_pairs(state: PlagiarismState) -> dict:
    """결정적 1차 정제: 임계 유사도 + 최소 fragment, 유사도 내림차순 top-K.
    (유저당 1건이라 self-pair는 이미 배제됨.)"""
    raw = state.get("dolos_pairs") or []
    kept = [
        p for p in raw
        if float(p.get("similarity", 0)) >= config.SIMILARITY_THRESHOLD
        and int(p.get("longest_fragment", 0)) >= config.MIN_FRAGMENT
    ]
    kept.sort(key=lambda p: float(p.get("similarity", 0)), reverse=True)
    return {"suspect_pairs": kept[: config.TOP_K]}


def persist_flags(state: PlagiarismState) -> dict:
    """의심 쌍을 plagiarism_pair(open)로 bulk 적재."""
    subs = {str(s["submission_id"]): s for s in (state.get("submissions") or [])}
    problem_id = state["problem_id"]
    run_id = state["run_id"]
    rows: list[dict] = []
    for p in state.get("suspect_pairs") or []:
        a = subs.get(str(p.get("a_id")))
        b = subs.get(str(p.get("b_id")))
        if not a or not b:
            continue
        row = {
            "run_id": run_id,
            "problem_id": problem_id,
            "submission_a_id": a["submission_id"],
            "submission_b_id": b["submission_id"],
            "user_a_id": a["user_id"],
            "user_b_id": b["user_id"],
            "similarity": float(p.get("similarity", 0)),
            "longest_fragment": int(p.get("longest_fragment", 0)),
            "total_overlap": int(p.get("total_overlap", 0)),
            "fragments": p.get("fragments") or [],
        }
        # Phase 2 멀티에이전트 판정 결과(있으면) — advisory.
        for k in ("agent_verdict", "agent_confidence", "agent_rationale", "agent_debate"):
            if p.get(k) is not None:
                row[k] = p[k]
        rows.append(row)
    ids = backend_client.insert_pairs(rows)
    return {"flagged_ids": ids}


def build_graph():
    g: StateGraph = StateGraph(PlagiarismState)
    g.add_node("fetch_submissions", fetch_submissions)
    g.add_node("run_dolos", run_dolos_node)
    g.add_node("screen_pairs", screen_pairs)
    g.add_node("persist_flags", persist_flags)
    g.set_entry_point("fetch_submissions")
    # 제출 2개 미만이면 비교 불가 → 바로 종료(빈 결과로 done 처리).
    g.add_conditional_edges(
        "fetch_submissions",
        lambda s: "continue" if len(s.get("submissions") or []) >= 2 else "end",
        {"continue": "run_dolos", "end": END},
    )
    g.add_edge("run_dolos", "screen_pairs")
    # Phase 2: 앙상블 on이면 screen → adjudicate(멀티에이전트) → persist, off면 screen → persist.
    if config.ENSEMBLE_ENABLED:
        g.add_node("adjudicate_pairs", adjudicate_pairs)
        g.add_edge("screen_pairs", "adjudicate_pairs")
        g.add_edge("adjudicate_pairs", "persist_flags")
    else:
        g.add_edge("screen_pairs", "persist_flags")
    g.add_edge("persist_flags", END)
    return g.compile()


# ── 실행 드라이버 (run 레코드 생성/마감까지) ──────────────────────────────
def run_plagiarism(problem_id: int) -> dict:
    """문제별 표절 검토 1회. run 레코드 생성 → 그래프 → run 마감. run 요약 dict 반환."""
    run_id = uuid.uuid4().hex
    backend_client.create_run({
        "id": run_id,
        "problem_id": problem_id,
        "problem_title": backend_client.problem_title(problem_id),
        "config": config.snapshot(),
    })
    t0 = time.monotonic()
    try:
        final = build_graph().invoke({"problem_id": problem_id, "run_id": run_id, "errors": []})
        subs = final.get("submissions") or []
        suspect = final.get("suspect_pairs") or []
        flagged = final.get("flagged_ids") or []
        backend_client.update_run(
            run_id,
            status="done",
            submission_count=len(subs),
            pair_count=len(suspect),
            flagged_count=len(flagged),
            total_duration_ms=int((time.monotonic() - t0) * 1000),
            ended_at=_now_iso(),
        )
        return {"run_id": run_id, "submissions": len(subs), "flagged": len(flagged)}
    except Exception as exc:  # noqa: BLE001 — run을 failed로 마감하고 재전파
        msg = f"{type(exc).__name__}: {exc}"
        log.exception("plagiarism run %s failed", run_id)
        try:
            backend_client.update_run(
                run_id, status="failed", errors=[msg],
                total_duration_ms=int((time.monotonic() - t0) * 1000), ended_at=_now_iso(),
            )
        except Exception:  # noqa: BLE001
            pass
        raise
