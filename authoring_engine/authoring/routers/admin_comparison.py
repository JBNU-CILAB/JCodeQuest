"""compare_to_original 노드가 authoring_meta.comparison에 적어 둔 3축 정량 기록을
admin dashboard용으로 노출. backend는 이 데이터를 opaque JSON으로 들고 있을 뿐이고,
구조화·집계는 이 라우터가 담당한다.

엔드포인트:
  GET /api/admin/problems/{problem_id}/comparison
      → 단일 변형(또는 원본)의 비교 점수
  GET /api/admin/originals/{original_id}/comparison
      → 한 원본의 모든 변형 점수 + 평균/최소/최대 집계
"""
from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam

from .. import backend_client
from ..admin_auth import require_admin
from ..api_models import (
    ComparisonAggregateOut,
    ComparisonStats,
    ProblemComparisonOut,
)

router = APIRouter(
    tags=["admin-comparison"],
    dependencies=[Depends(require_admin)],
)


def _coerce_score(v: Any) -> float | None:
    """authoring_meta는 opaque dict — 타입을 한 번 더 방어. 잘못된 형이면 null."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    return None


def _row_to_comparison(admin: dict[str, Any]) -> ProblemComparisonOut:
    meta = admin.get("authoring_meta") or {}
    comp = meta.get("comparison") or {}
    return ProblemComparisonOut(
        problem_id=admin["id"],
        parent_id=admin.get("parent_id"),
        title=admin.get("title", ""),
        level=admin.get("level", ""),
        hallucination_score=_coerce_score(comp.get("hallucination_score")),
        intent_similarity=_coerce_score(comp.get("intent_similarity")),
        difficulty_similarity=_coerce_score(comp.get("difficulty_similarity")),
        rationale=str(comp.get("rationale") or ""),
        error=str(comp.get("error") or ""),
        judge_score=_coerce_score(meta.get("judge_score")),
        solver_passed=(
            bool(meta["solver_passed"]) if isinstance(meta.get("solver_passed"), bool) else None
        ),
    )


def _stats_of(values: list[float | None]) -> ComparisonStats:
    nums = [v for v in values if v is not None]
    if not nums:
        return ComparisonStats(count=0, mean=None, min=None, max=None)
    return ComparisonStats(
        count=len(nums),
        mean=round(sum(nums) / len(nums), 3),
        min=round(min(nums), 3),
        max=round(max(nums), 3),
    )


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(
        status_code=e.response.status_code,
        detail=f"backend: {e.response.text[:200]}",
    )


@router.get(
    "/api/admin/problems/{problem_id}/comparison",
    response_model=ProblemComparisonOut,
    summary="단일 변형의 compare_to_original 점수",
    description=(
        "compare_to_original 노드가 돌지 않은 변형(예: 수동 등록 원본, "
        "solver_passed 이전 단계에서 멈춘 후보)은 점수 필드가 모두 null로 채워진다."
    ),
    responses={404: {"description": "문제 없음"}},
)
async def get_problem_comparison(
    problem_id: Annotated[int, PathParam(description="문제 ID")],
) -> ProblemComparisonOut:
    try:
        admin = backend_client.fetch_problem(problem_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    return _row_to_comparison(admin.model_dump())


@router.get(
    "/api/admin/originals/{original_id}/comparison",
    response_model=ComparisonAggregateOut,
    summary="한 원본의 모든 변형에 대한 비교 점수 집계",
    description=(
        "지정한 원본 문제의 모든 자식 변형을 끌어와 3축 평균/최소/최대를 계산하고, "
        "개별 엔트리도 함께 반환한다. compare 노드가 돌지 않은 변형은 집계에서 "
        "제외(count 감소)되지만 variants 목록에는 점수=null로 포함된다."
    ),
    responses={404: {"description": "원본 없음"}},
)
async def get_original_comparison_aggregate(
    original_id: Annotated[int, PathParam(description="원본 문제 ID")],
) -> ComparisonAggregateOut:
    try:
        original = backend_client.fetch_problem(original_id)
        children = backend_client.list_children(original_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)

    entries = [_row_to_comparison(c.model_dump()) for c in children]
    return ComparisonAggregateOut(
        original_id=original.id,
        original_title=original.title,
        variant_count=len(entries),
        scored_count=sum(1 for e in entries if e.hallucination_score is not None),
        hallucination=_stats_of([e.hallucination_score for e in entries]),
        intent_similarity=_stats_of([e.intent_similarity for e in entries]),
        difficulty_similarity=_stats_of([e.difficulty_similarity for e in entries]),
        variants=entries,
    )
