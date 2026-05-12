from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from jcq_shared.schemas import IntentRubric, Problem, ProblemLevel, TestCase

__all__ = ["IntentRubric", "Problem", "ProblemLevel", "TestCase"]

Verdict = Literal["AC", "SUS"]
EnsembleVerdict = Literal["AC", "SUS"]
EnsembleMode = Literal["unanimous", "majority"]
ExecStatus = Literal["OK", "TLE", "MLE", "RE"]


class ExecResult(BaseModel):
    status: ExecStatus = Field(
        description="실행 종료 분류 — OK(정상), TLE(시간초과), MLE(메모리초과), RE(런타임에러)",
    )
    stdout: str = Field(default="", description="표준출력 (최대 64 KiB)")
    stderr: str = Field(default="", description="표준에러 (최대 64 KiB)")
    exit_code: int | None = Field(
        default=None, description="프로세스 종료 코드. 비정상 종료 시 None일 수 있음."
    )
    elapsed_ms: int = Field(default=0, description="실행 소요 시간 (ms)")
    peak_memory_kb: int = Field(default=0, description="피크 메모리 사용량 (KB)")


class TestResult(BaseModel):
    ordinal: int = Field(description="테스트 케이스 순번 (1부터)", examples=[1])
    passed: bool = Field(description="해당 케이스 통과 여부", examples=[True])
    status: ExecStatus = Field(
        default="OK", description="실행 분류 — passed=False일 때만 OK 외 값 가능"
    )
    actual_stdout: str | None = Field(
        default=None, description="실제 표준출력 (스니펫). 실패 시 비교용으로 노출."
    )
    error: str | None = Field(
        default=None, description="RE 등 비정상 종료 시 stderr 요약"
    )
    elapsed_ms: int = Field(default=0, description="이 케이스 실행 시간 (ms)")
    peak_memory_kb: int = Field(default=0, description="이 케이스 피크 메모리 (KB)")


class Submission(BaseModel):
    id: int
    user_id: int
    problem_id: int
    code: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class JudgeVotePartial(BaseModel):
    """LLM이 직접 채우는 필드만 담는 스키마. judge_id는 호출자가 주입."""

    verdict: Verdict = Field(
        description="이 심판의 판정 — AC(합격) 또는 SUS(의심)"
    )
    intent_match: bool = Field(
        description="제출 코드가 출제 의도(rubric)와 일치한다고 보는지"
    )
    rationale: str = Field(description="판정 근거 (자연어)")
    confidence: float = Field(ge=0.0, le=1.0, description="0.0–1.0 신뢰도")


class JudgeVote(JudgeVotePartial):
    judge_id: str = Field(
        description="모델 식별자 (Melchior | Balthasar | Casper)",
        examples=["Melchior"],
    )


class EnsembleResult(BaseModel):
    final_verdict: EnsembleVerdict = Field(
        description="3명의 심판 투표를 종합한 최종 판정"
    )
    mode: EnsembleMode = Field(
        description="unanimous=3/3 동일, majority=2/3 다수결"
    )
    votes: list[JudgeVote] = Field(description="개별 심판의 판정 목록 (3개)")


JobStatus = Literal["queued", "running", "done", "failed"]

# 제출 코드 길이 상한 — 알고리즘 풀이는 통상 수 KB. 페이로드 폭주로 DB·메모리를 흔드는
# 케이스 차단. 변경 시 storage.submissions.MAX_ATTEMPTS와 무관.
MAX_CODE_LENGTH = 64 * 1024


class GradeRequest(BaseModel):
    """user_id는 인증된 세션에서 추출 — body로 받지 않음(위조 차단)."""

    problem_id: int = Field(description="채점할 문제 ID", examples=[1])
    code: str = Field(
        min_length=1,
        max_length=MAX_CODE_LENGTH,
        description="제출할 Python 소스 — UTF-8, 최대 64 KiB",
        examples=["n = int(input())\nprint(n * 2)\n"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "problem_id": 1,
                    "code": "n = int(input())\nprint(n * 2)\n",
                }
            ]
        }
    )


class GradeAcceptedResponse(BaseModel):
    submission_id: int = Field(
        description="생성된 제출 ID — 이후 /grade/{id} 또는 SSE에서 사용",
        examples=[42],
    )
    status: JobStatus = Field(
        default="queued", description="제출 직후 상태 — 항상 queued"
    )


class SubmissionStatusResponse(BaseModel):
    submission_id: int = Field(examples=[42])
    status: JobStatus = Field(description="채점 진행 상태")
    final_verdict: EnsembleVerdict | None = Field(
        default=None, description="채점 완료 후의 최종 판정 (status=done일 때만)"
    )
    test_results: list[TestResult] | None = Field(
        default=None, description="테스트 케이스별 결과 — sandbox 실행 후 채워짐"
    )
    ensemble: EnsembleResult | None = Field(
        default=None,
        description="3-judge 앙상블 결과 — 모든 케이스 통과 시에만 채워짐",
    )
    points_awarded: int | None = Field(
        default=None,
        description="첫 AC일 때 사용자 EXP에 가산된 점수. 그 외엔 0 또는 None.",
        examples=[100],
    )


class PublicTestCase(BaseModel):
    """학생에게 노출되는 샘플 케이스. hidden 케이스의 stdin/expected는 절대 포함하지 않음."""

    ordinal: int = Field(description="테스트 순번", examples=[1])
    stdin: str = Field(description="표준입력 (개행 포함)")
    expected_stdout: str = Field(description="기대 표준출력 (개행 trim)")


class ProblemSummary(BaseModel):
    """목록용 — reference_code / intent_rubric 내부는 제외."""

    id: int = Field(examples=[1])
    title: str = Field(description="문제 제목", examples=["두 배 출력"])
    category: str = Field(description="카테고리 슬러그", examples=["basic"])
    level: Literal["bronze", "silver", "gold"] = Field(
        description="난이도"
    )
    points: int = Field(
        description="기본 배점 — 첫 AC 시 EXP로 가산 (효율 보너스 별도)",
        examples=[100],
    )
    one_line_summary: str = Field(description="한 줄 요약")
    iso_week: str = Field(
        description=(
            "출제 주차 라벨 'YYYY-Www' (ISO 8601). "
            "주차별 화면이 한 번의 목록 응답으로 라벨까지 그릴 수 있게 포함."
        ),
        examples=["2026-W19"],
    )


class WeeklyProblemBucket(BaseModel):
    """주차 인덱스 — 'YYYY-Www'와 그 주에 출제된 approved 문제 수."""

    week: str = Field(
        description="ISO 8601 주차 라벨 'YYYY-Www'", examples=["2026-W19"]
    )
    count: int = Field(
        description="해당 주에 출제된 approved 문제 수", examples=[3]
    )


class WeeklyProblemBucketsResponse(BaseModel):
    buckets: list[WeeklyProblemBucket] = Field(
        description="ISO 주차 내림차순(최신 주가 먼저) 정렬"
    )


class ProblemDetail(BaseModel):
    """상세 — statement와 샘플 케이스만 공개. 채점 기준/정답 코드는 비공개."""

    id: int
    title: str
    statement: str = Field(description="문제 본문 (Markdown 허용)")
    category: str
    level: Literal["bronze", "silver", "gold"]
    points: int
    time_limit_ms: int = Field(description="실행 시간 제한 (ms)", examples=[2000])
    memory_limit_mb: int = Field(
        description="메모리 제한 (MB)", examples=[256]
    )
    one_line_summary: str
    sample_test_cases: list[PublicTestCase] = Field(
        default_factory=list,
        description="공개 샘플 케이스 — hidden 케이스는 포함하지 않음",
    )


class AttemptStatusResponse(BaseModel):
    """제출 화면이 '남은 시도 횟수 / 쿨다운 / AC 여부'를 한 번에 보고 그릴 수 있도록 묶음."""

    problem_id: int
    attempts: int = Field(description="누적 제출 횟수", examples=[2])
    remaining: int = Field(
        description="남은 시도 횟수 (max_attempts - attempts)", examples=[8]
    )
    max_attempts: int = Field(description="문제당 최대 시도 횟수", examples=[10])
    solved: bool = Field(description="이미 AC를 받은 적이 있는지")
    cooldown_remaining_s: float = Field(
        description="다음 제출까지 남은 쿨다운 초. 0 이하면 즉시 가능."
    )
    can_submit: bool = Field(
        description="현재 시점에 제출 가능 여부 (solved=False & remaining>0 & cooldown<=0)"
    )


class SubmissionListItem(BaseModel):
    """본인 제출 목록용 — code는 페이로드 비대해서 제외. 상세는 /grade/{id}로."""

    id: int = Field(description="제출 ID")
    problem_id: int
    status: JobStatus
    final_verdict: EnsembleVerdict | None = None
    mode: EnsembleMode | None = Field(
        default=None,
        description="앙상블 모드 (unanimous|majority). 앙상블 미실행이면 null.",
    )
    points_awarded: int | None = None
    max_elapsed_ms: int | None = Field(
        default=None, description="모든 케이스 중 최대 실행 시간 (ms)"
    )
    peak_memory_kb: int | None = Field(
        default=None, description="모든 케이스 중 최대 메모리 (KB)"
    )
    created_at: datetime


class SubmissionListResponse(BaseModel):
    items: list[SubmissionListItem]
    total: int = Field(description="필터 적용 후 전체 건수")
    limit: int
    offset: int


class MeResponse(BaseModel):
    """GET /me 의 응답 — UserRow의 공개 가능한 필드만."""

    id: int = Field(examples=[1])
    display_name: str = Field(examples=["김민석"])
    email: str = Field(examples=["foo@jbnu.ac.kr"])
    provider: Literal["google", "dev_stub"] = Field(
        description="인증 공급자"
    )
    exp: int = Field(description="누적 경험치", examples=[1500])
    tier: str = Field(description="현재 티어 (exp 기반 산출)")


LeaderboardPeriod = Literal["all", "week"]


class LeaderboardEntry(BaseModel):
    """리더보드 한 행. period에 따라 points 의미가 달라진다."""

    rank: int = Field(description="1부터 시작하는 순위 (동점이면 user_id 오름차순)")
    user_id: int = Field(examples=[1])
    display_name: str = Field(examples=["김민석"])
    tier: str = Field(description="현재 티어")
    points: int = Field(
        description=(
            "period=all이면 누적 EXP, period=week면 이번 ISO 주차에 처음 AC로 획득한 "
            "points_awarded 합"
        ),
        examples=[1500],
    )


class LeaderboardResponse(BaseModel):
    period: LeaderboardPeriod = Field(description="all=전체 누적, week=이번 ISO 주차")
    week: str | None = Field(
        default=None,
        description="period=week일 때만 채워짐. 집계 대상 ISO 주차 'YYYY-Www'.",
        examples=["2026-W19"],
    )
    entries: list[LeaderboardEntry] = Field(
        description="points 내림차순. 동점은 user_id 오름차순으로 안정 정렬."
    )


class TutorResponse(BaseModel):
    submission_id: int
    message: str = Field(description="튜터가 생성한 한국어 가이드 메시지")


class TutorHistoryItem(BaseModel):
    id: int = Field(description="tutor_message 행 ID")
    message: str
    created_at: datetime


class TutorHistoryResponse(BaseModel):
    submission_id: int
    messages: list[TutorHistoryItem] = Field(
        description="생성 시각 오름차순"
    )
