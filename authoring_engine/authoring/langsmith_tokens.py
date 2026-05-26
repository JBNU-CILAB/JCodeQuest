"""LangSmith 트레이스 → 파이프라인 노드별 토큰 사용량 집계.

LangGraph는 노드마다 span(run)을 만들고, 노드 함수 이름(= NODE_ORDER 키)으로 명명한다.
LLM 호출은 그 노드 span의 하위 span(run_type="llm")으로 들어가며 토큰 수치를 가진다.
따라서 노드 토큰 = 그 노드 span 서브트리의 **llm 리프 span 토큰 합**.

부모 span의 total_tokens는 집계값이라 더하면 중복되므로 run_type=="llm"만 합산한다.
스트림 청크엔 토큰이 없어 0으로 저장되며, run 종료 후 LangSmith 인제스트가 끝나면
상세 조회 시 lazy하게 채운다(routers/runs.py). 모든 실패는 fail-open({} 반환).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .pipeline.node_stats import NODE_ORDER

log = logging.getLogger(__name__)

_NODE_KEYS = set(NODE_ORDER)


def _tok(v: Any) -> int:
    return v if isinstance(v, int) and v > 0 else 0


def aggregate_node_tokens(
    spans: list[dict[str, Any]],
    node_keys: set[str] = _NODE_KEYS,
) -> dict[str, dict[str, int]]:
    """span dict 목록 → {node_key: {prompt, completion, total}}.

    각 span: {id, parent_run_id, name, run_type, prompt, completion, total}.
    노드 span(name이 node_keys에 속함)의 서브트리에서 run_type=="llm" span의 토큰을 합산.
    같은 노드가 재시도로 여러 번 나타나면 모두 합산. 순수 함수 — 테스트 용이.
    """
    by_id: dict[str, dict[str, Any]] = {}
    children: dict[str | None, list[str]] = {}
    for s in spans:
        sid = s.get("id")
        if sid is None:
            continue
        by_id[sid] = s
        children.setdefault(s.get("parent_run_id"), []).append(sid)

    def subtree_llm_tokens(root_id: str) -> dict[str, int]:
        acc = {"prompt": 0, "completion": 0, "total": 0}
        stack = [root_id]
        while stack:
            cur = by_id.get(stack.pop())
            if not cur:
                continue
            stack.extend(children.get(cur["id"], []))
            if cur.get("run_type") == "llm":
                p, c = _tok(cur.get("prompt")), _tok(cur.get("completion"))
                t = _tok(cur.get("total")) or (p + c)
                acc["prompt"] += p
                acc["completion"] += c
                acc["total"] += t
        return acc

    out: dict[str, dict[str, int]] = {}
    for s in spans:
        name = s.get("name")
        if name not in node_keys:
            continue
        tok = subtree_llm_tokens(s["id"])
        if name in out:
            for k in ("prompt", "completion", "total"):
                out[name][k] += tok[k]
        else:
            out[name] = tok
    # 토큰이 0인 노드는 의미 없으니 제외
    return {k: v for k, v in out.items() if v["total"] > 0}


def _fetch_spans(trace_id: str, project: str) -> list[dict[str, Any]]:
    from langsmith import Client

    client = Client()
    runs = list(client.list_runs(project_name=project, trace_id=trace_id))
    spans: list[dict[str, Any]] = []
    for r in runs:
        spans.append({
            "id": str(r.id),
            "parent_run_id": str(r.parent_run_id) if r.parent_run_id else None,
            "name": r.name,
            "run_type": r.run_type,
            "prompt": getattr(r, "prompt_tokens", None),
            "completion": getattr(r, "completion_tokens", None),
            "total": getattr(r, "total_tokens", None),
        })
    return spans


def node_token_usage(trace_id: str | None) -> dict[str, dict[str, int]]:
    """trace_id의 노드별 토큰 사용량. LANGSMITH 미설정/실패 시 fail-open {}."""
    if not trace_id or not os.getenv("LANGSMITH_API_KEY"):
        return {}
    project = os.getenv("LANGSMITH_PROJECT", "jcq-authoring")
    try:
        spans = _fetch_spans(trace_id, project)
    except Exception as exc:  # noqa: BLE001 — fail-open
        log.warning("LangSmith 토큰 조회 실패(무시) trace=%s: %s", trace_id, exc)
        return {}
    return aggregate_node_tokens(spans)
