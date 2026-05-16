"""DB가 모듈 import 시점에 engine을 생성하므로, src를 import하기 전에
JCQ_DB_URL을 임시 파일 경로로 박아둬야 테스트가 격리된다."""
import os
import sys
import tempfile
import uuid
from pathlib import Path

# 1) 임시 DB 파일
_db_fd, _db_path = tempfile.mkstemp(prefix="jcq_test_", suffix=".db")
os.close(_db_fd)
os.environ["JCQ_DB_URL"] = f"sqlite:///{_db_path}"
# storage/db.py는 비-Postgres URL을 거부한다(vault plaintext fallback 방지).
# 테스트는 SQLite 격리가 필요하므로 명시적으로 우회 플래그를 켠다.
os.environ["JCQ_ALLOW_NON_POSTGRES"] = "1"

# 1.5) auth 관련 env — dev-login 라우트 등록이 module import 시점에 env를 읽으므로 여기서 미리 주입.
os.environ.setdefault("JCQ_AUTH_ALLOW_DEV_STUB", "1")
# TestClient는 http로 붙으므로 Secure 쿠키는 클라이언트가 실어주지 않는다 — 끄지 않으면 /me에서 401.
os.environ.setdefault("JCQ_COOKIE_INSECURE", "1")
# 테스트용 JWT 시크릿 (Bearer JWT를 이용하는 테스트에서 사용)
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-supabase-jwt-secret-32chars!!")

# 1.6) 개발용 앙상블 스킵 플래그가 셸/.env에서 leak되면 ensemble을 monkeypatch하는
# pipeline 테스트들이 실패한다 — 빈 문자열로 명시 설정 (load_dotenv는 override=False라
# 이미 set된 env는 덮어쓰지 않음).
os.environ["JCQ_SKIP_ENSEMBLE"] = ""

# 2) backend/ 를 sys.path에 추가 — src.* 임포트용
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# 2.5) judge_engine/ 도 path에 — 통합 테스트가 채점 엔진을 띄우지 않고
# 인-프로세스 샌드박스로 mock 하기 위함. judge.* import용.
_JUDGE_ENGINE = BACKEND.parent / "judge_engine"
if _JUDGE_ENGINE.is_dir():
    sys.path.insert(0, str(_JUDGE_ENGINE))

import pytest  # noqa: E402

from src.schemas import IntentRubric, Problem, TestCase  # noqa: E402
from src.storage import init_db  # noqa: E402
from src.storage.problems import create_problem  # noqa: E402
from src.storage.users import get_or_create_user  # noqa: E402
from src.storage import get_session  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db():
    init_db()
    yield
    try:
        os.unlink(_db_path)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _disable_cooldown(monkeypatch):
    """기존 슈트는 빠른 연속 제출을 검사하므로 쿨다운 0으로 떨어뜨림.
    쿨다운 자체를 검사하는 테스트는 자기 fixture에서 다시 켠다."""
    import src.storage.submissions as subs  # noqa: PLC0415
    monkeypatch.setattr(subs, "SUBMISSION_COOLDOWN_S", 0.0)


@pytest.fixture
def sample_problem() -> Problem:
    """입력 n을 받아 2*n을 출력하는 단순 문제."""
    return Problem(
        id=0,  # placeholder; DB에서 새 id 부여
        title="2배 출력",
        statement="정수 n이 입력되면 2*n을 출력하라.",
        category="basic",
        level="bronze",
        points=100,
        time_limit_ms=1000,
        memory_limit_mb=128,
        reference_code="n = int(input())\nprint(n * 2)\n",
        intent_rubric=IntentRubric(
            expected_approach="입력을 정수로 파싱 후 2배",
            expected_complexity="O(1)",
            must_handle=["0", "음수"],
            forbidden_patterns=["하드코딩"],
            key_insight="단순 산술",
            one_line_summary="n*2 출력",
        ),
        test_cases=[
            TestCase(ordinal=1, stdin="3\n", expected_stdout="6", is_sample=True),
            TestCase(ordinal=2, stdin="0\n", expected_stdout="0"),
            TestCase(ordinal=3, stdin="-5\n", expected_stdout="-10"),
        ],
    )


@pytest.fixture
def seeded_problem_id(sample_problem: Problem) -> int:
    with get_session() as s:
        return create_problem(s, sample_problem, status="approved")


@pytest.fixture
def login_as():
    """TestClient에 dev-login 쿠키 세팅 헬퍼. 멀티유저 시나리오는 cookies.clear() 후 재호출.

    같은 email로 다시 부르면 같은 user (provider=dev_stub의 external_id가 email).
    호출 시 새 SessionRow가 생기고 쿠키가 갱신된다."""
    from fastapi.testclient import TestClient

    def _login(client: TestClient, email: str = "test@example.com", name: str = "test") -> int:
        r = client.post("/auth/dev-login", params={"email": email, "name": name})
        assert r.status_code == 200, r.text
        return r.json()["user_id"]

    return _login


@pytest.fixture
def make_user():
    """Submission/Tutor 테스트용 헬퍼 — FK 충족용 User 행을 그때그때 만들어 id 반환.
    external_id는 uuid로 매 호출 unique → 같은 fixture 안에서 여러 번 부르면 별도 유저."""

    def _make(display_name: str | None = None, *, email: str | None = None) -> int:
        ext = uuid.uuid4().hex[:12]
        with get_session() as s:
            u = get_or_create_user(
                s,
                provider="dev_stub",
                external_id=f"test-{ext}",
                display_name=display_name or f"테스트유저-{ext}",
                email=email,
            )
            assert u.id is not None
            return u.id

    return _make


@pytest.fixture
def mock_engine(monkeypatch):
    """채점 엔진 큐잉 호출(`submit_to_engine`)을 인-프로세스 샌드박스 + 직접 webhook 적용으로 대체.

    실제 흐름:
        POST /grade → submit_to_engine(httpx) → judge_engine 큐 → webhook → apply_grading_event
    테스트 흐름:
        POST /grade → submit_to_engine(mock) → asyncio.create_task로
                       샌드박스 실행 + (옵션) vote → apply_grading_event(running) → apply_grading_event(done)

    사용:
        def test_x(mock_engine, ...):
            mock_engine.set_vote(fake_vote_fn)  # 전부 통과 시에만 호출됨
    """
    import asyncio as _asyncio

    from judge.sandbox import run_all_tests  # judge_engine/judge — sys.path 부트스트랩됨

    from src.judge.jobs import apply_grading_event
    from src.schemas import GradeEvent

    state: dict = {"vote_fn": None, "tasks": []}

    async def _simulate_grading(submission_id, problem, code, app):
        # webhook이 도착하는 순서를 흉내내기 위해 running을 먼저 발행.
        broker = app.state.events
        apply_grading_event(
            GradeEvent(submission_id=submission_id, event="running"),
            events=broker,
        )

        try:
            test_results = await _asyncio.to_thread(
                run_all_tests,
                code,
                problem.test_cases,
                time_limit_ms=problem.time_limit_ms,
                memory_limit_mb=problem.memory_limit_mb,
            )
            all_passed = bool(test_results) and all(r.passed for r in test_results)
            ensemble = None
            if all_passed and state["vote_fn"] is not None:
                ensemble = await state["vote_fn"](problem, code, test_results)
            apply_grading_event(
                GradeEvent(
                    submission_id=submission_id,
                    event="done",
                    test_results=test_results,
                    all_passed=all_passed,
                    ensemble=ensemble,
                ),
                events=broker,
            )
        except Exception as e:  # noqa: BLE001
            apply_grading_event(
                GradeEvent(
                    submission_id=submission_id,
                    event="failed",
                    error=f"{type(e).__name__}: {e}",
                ),
                events=broker,
            )

    async def _fake_submit(submission_id, problem, code):
        # `/grade` 핸들러 컨텍스트에서 app을 얻으려고 현재 task의 컨텍스트를 활용.
        # TestClient 환경에선 monkeypatch한 app 인스턴스를 직접 끌어옴.
        from src.main import app

        t = _asyncio.create_task(_simulate_grading(submission_id, problem, code, app))
        state["tasks"].append(t)

    import src.api.grading as grading_api
    monkeypatch.setattr(grading_api, "submit_to_engine", _fake_submit)

    class _Handle:
        def set_vote(self, fn) -> None:
            state["vote_fn"] = fn

    return _Handle()
