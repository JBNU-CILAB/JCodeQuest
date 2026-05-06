from fastapi import APIRouter, HTTPException, Request, status as http_status

from ..judge.jobs import grade_submission
from ..schemas import (
    EnsembleResult,
    GradeAcceptedResponse,
    GradeRequest,
    JudgeVote,
    SubmissionStatusResponse,
    TestResult,
)
from ..storage import get_session
from ..storage.problems import get_problem
from ..storage.submissions import (
    MAX_ATTEMPTS,
    attempt_status,
    create_submission,
    get_submission,
)

router = APIRouter(prefix="/grade", tags=["grading"])


@router.post(
    "",
    status_code=http_status.HTTP_202_ACCEPTED,
    response_model=GradeAcceptedResponse,
)
async def submit_grade(
    req: GradeRequest, request: Request
) -> GradeAcceptedResponse:
    with get_session() as session:
        problem = get_problem(session, req.problem_id)
        if problem is None:
            raise HTTPException(404, f"problem {req.problem_id} not found")

        astatus = attempt_status(session, req.user_id, req.problem_id)
        if astatus.solved:
            raise HTTPException(409, "이미 해결한 문제입니다")
        if astatus.attempts >= MAX_ATTEMPTS:
            raise HTTPException(
                429, f"최대 제출 횟수({MAX_ATTEMPTS}회) 초과"
            )

        submission_id = create_submission(
            session,
            user_id=req.user_id,
            problem_id=req.problem_id,
            code=req.code,
        )

    queue = request.app.state.queue
    code = req.code
    await queue.submit(lambda: grade_submission(submission_id, problem, code))

    return GradeAcceptedResponse(submission_id=submission_id, status="queued")


@router.get("/{submission_id}", response_model=SubmissionStatusResponse)
async def get_grade(submission_id: int) -> SubmissionStatusResponse:
    with get_session() as session:
        sub = get_submission(session, submission_id)
        if sub is None:
            raise HTTPException(404, f"submission {submission_id} not found")

        ensemble = None
        if sub.mode is not None and sub.votes is not None:
            ensemble = EnsembleResult(
                final_verdict=sub.final_verdict,  # type: ignore[arg-type]
                mode=sub.mode,  # type: ignore[arg-type]
                votes=[JudgeVote(**v) for v in sub.votes],
            )

        test_results = (
            [TestResult(**t) for t in sub.test_results]
            if sub.test_results is not None
            else None
        )

        return SubmissionStatusResponse(
            submission_id=submission_id,
            status=sub.status,  # type: ignore[arg-type]
            final_verdict=sub.final_verdict,  # type: ignore[arg-type]
            test_results=test_results,
            ensemble=ensemble,
            points_awarded=sub.points_awarded,
        )
