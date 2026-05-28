"""문제 조회/등록 라우터 — 모두 backend /internal/*에 위임."""
from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Query
from jcq_shared.schemas import (
    AuthoringProblemUpdate,
    IntentRubric,
    Problem,
    ProblemDeleteResponse,
    TestCase,
)

from .. import backend_client
from ..admin_auth import require_admin
from ..api_models import (
    CreateOriginalRequest,
    CreateOriginalResponse,
    ProblemDetailOut,
    ProblemSummaryOut,
    UpdateProblemRequest,
)

router = APIRouter(tags=["problems"], dependencies=[Depends(require_admin)])


def _admin_to_summary(admin: dict[str, Any]) -> dict[str, Any]:
    """backend AuthoringProblemSummary/Admin 응답을 viewer 응답 모델로 매핑."""
    return {
        "id": admin["id"],
        "title": admin["title"],
        "category": admin["category"],
        "level": admin["level"],
        "status": admin["status"],
        "parent_id": admin.get("parent_id"),
        "langsmith_trace_id": admin.get("langsmith_trace_id"),
        "created_at": admin.get("created_at"),
        "child_count": admin.get("child_count", 0),
        "avg_judge_score": admin.get("avg_judge_score"),
    }


def _admin_to_detail(admin: dict[str, Any]) -> dict[str, Any]:
    base = _admin_to_summary(admin)
    base.update(
        {
            "statement": admin["statement"],
            "reference_code": admin["reference_code"],
            "intent_rubric": admin.get("intent_rubric"),
            "authoring_meta": admin.get("authoring_meta"),
            "points": admin["points"],
            "time_limit_ms": admin["time_limit_ms"],
            "memory_limit_mb": admin["memory_limit_mb"],
            "test_cases": admin.get("test_cases", []),
        }
    )
    return base


def _backend_error(e: httpx.HTTPStatusError) -> HTTPException:
    """backend가 돌려준 4xx/5xx를 그대로 transport — 메시지에 원본 status 포함."""
    return HTTPException(
        status_code=e.response.status_code,
        detail=f"backend: {e.response.text[:200]}",
    )


@router.get(
    "/api/problems",
    response_model=list[ProblemSummaryOut],
    summary="문제 목록 (변형 통계 포함)",
)
async def list_problems(
    originals_only: Annotated[
        bool, Query(description="false면 변형까지 모두 포함")
    ] = True,
) -> list[dict[str, Any]]:
    try:
        rows = backend_client.list_problems(originals_only=originals_only)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    return [_admin_to_summary(r.model_dump()) for r in rows]


@router.get(
    "/api/problems/{problem_id}",
    response_model=ProblemDetailOut,
    summary="문제 상세 (관리자 시야)",
    responses={404: {"description": "문제 없음"}},
)
async def get_problem_detail(
    problem_id: Annotated[int, PathParam(description="문제 ID")]
) -> dict[str, Any]:
    try:
        admin = backend_client.fetch_problem(problem_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    return _admin_to_detail(admin.model_dump())


@router.post(
    "/api/problems",
    response_model=CreateOriginalResponse,
    summary="원본 문제 직접 등록 (출제 엔진 우회)",
    description=(
        "운영자/시드 용도. `expected_stdout`이 비어 있으면 judge_engine 샌드박스에서 "
        "reference_code를 실행해 자동으로 채운다. 그 후 backend에 POST해 저장한다."
    ),
    responses={
        400: {"description": "test_cases 비었거나 level 부정"},
        422: {"description": "autofill 실패 — case <i>: <status>"},
    },
)
async def create_original(req: CreateOriginalRequest) -> dict[str, Any]:
    if not req.test_cases:
        raise HTTPException(400, "test_cases 최소 1개 필요")
    if req.level not in ("bronze", "silver", "gold"):
        raise HTTPException(400, "level은 bronze|silver|gold")

    filled: list[TestCase] = []
    autofill_log: list[dict[str, Any]] = []
    for i, tc in enumerate(req.test_cases, start=1):
        stdin = tc.stdin if tc.stdin.endswith("\n") or not tc.stdin else tc.stdin + "\n"
        expected = tc.expected_stdout
        if not expected:
            r = backend_client.sandbox_run(
                req.reference_code,
                stdin,
                time_limit_ms=req.time_limit_ms,
                memory_limit_mb=req.memory_limit_mb,
            )
            if r.status != "OK":
                raise HTTPException(
                    422,
                    f"autofill 실패 — case {i}: {r.status} stderr={r.stderr[:200]!r}",
                )
            expected = r.stdout.rstrip()
            autofill_log.append(
                {"ordinal": i, "elapsed_ms": r.elapsed_ms, "expected": expected[:80]}
            )
        filled.append(
            TestCase(ordinal=i, stdin=stdin, expected_stdout=expected, is_sample=tc.is_sample)
        )

    rubric = IntentRubric(
        expected_approach=req.expected_approach or req.one_line_summary or req.title,
        expected_complexity=req.expected_complexity or "O(1)",
        must_handle=req.must_handle,
        forbidden_patterns=req.forbidden_patterns,
        key_insight=req.key_insight or req.one_line_summary or req.title,
        one_line_summary=req.one_line_summary or req.title,
    )

    problem = Problem(
        id=0,
        title=req.title,
        statement=req.statement,
        category=req.category,
        level=req.level,  # type: ignore[arg-type]
        points=req.points,
        time_limit_ms=req.time_limit_ms,
        memory_limit_mb=req.memory_limit_mb,
        reference_code=req.reference_code,
        intent_rubric=rubric,
        test_cases=filled,
    )

    meta: dict[str, Any] = {"source": "manual"}
    if autofill_log:
        meta["autofill"] = autofill_log

    try:
        pid = backend_client.create_problem(
            problem,
            status="approved",
            parent_id=None,
            authoring_meta=meta,
        )
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)

    return {"id": pid, "autofill": autofill_log}


@router.get(
    "/api/problems/{problem_id}/children",
    response_model=list[ProblemDetailOut],
    summary="원본의 변형 목록 (상세)",
)
async def list_problem_children(
    problem_id: Annotated[int, PathParam(description="원본 문제 ID")]
) -> list[dict[str, Any]]:
    try:
        rows = backend_client.list_children(problem_id)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    return [_admin_to_detail(r.model_dump()) for r in rows]


@router.patch(
    "/api/problems/{problem_id}",
    response_model=ProblemDetailOut,
    summary="문제 부분 수정 (admin)",
    description=(
        "주어진 필드만 수정한다. test_cases가 포함되면 기존 케이스를 전체 교체. "
        "intent_rubric 수정은 현재 비공개 (수동 등록 원본은 backend 정책상 메타 그대로 유지)."
    ),
    responses={404: {"description": "문제 없음"}},
)
async def update_problem_route(
    problem_id: Annotated[int, PathParam(description="수정 대상 문제 ID")],
    req: UpdateProblemRequest,
) -> dict[str, Any]:
    # 클라이언트가 보낸 필드만 추려서 그대로 전송. test_cases는 도메인 객체로 변환.
    sent = req.model_dump(exclude_unset=True, exclude={"test_cases"})
    payload_kwargs: dict[str, Any] = dict(sent)
    if req.test_cases is not None:
        # stdin 끝에 개행 자동 부착 — sandbox/judge가 stdin 끝 개행을 기대.
        payload_kwargs["test_cases"] = [
            TestCase(
                ordinal=tc.ordinal,
                stdin=tc.stdin if (not tc.stdin or tc.stdin.endswith("\n")) else tc.stdin + "\n",
                expected_stdout=tc.expected_stdout,
                is_sample=tc.is_sample,
            )
            for tc in req.test_cases
        ]
    payload = AuthoringProblemUpdate(**payload_kwargs)
    try:
        updated = backend_client.update_problem(problem_id, payload)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
    return _admin_to_detail(updated.model_dump())


@router.delete(
    "/api/problems/{problem_id}",
    response_model=ProblemDeleteResponse,
    summary="문제 + 변형/제출/튜터 하드 cascade 삭제",
    description=(
        "backend `/internal/problems/{id}` DELETE 로 위임. 자식 변형까지 함께 삭제하려면 "
        "`cascade_children=true` (기본). false면 자식이 있을 때 FK violation으로 실패."
    ),
    responses={404: {"description": "문제 없음"}},
)
async def delete_original(
    problem_id: Annotated[int, PathParam(description="삭제할 문제 ID")],
    cascade_children: Annotated[bool, Query(description="변형(자식)까지 같이 삭제")] = True,
) -> ProblemDeleteResponse:
    try:
        return backend_client.delete_problem(problem_id, cascade_children=cascade_children)
    except httpx.HTTPStatusError as e:
        raise _backend_error(e)
