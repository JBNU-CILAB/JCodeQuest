import os
import sys
from pathlib import Path

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
JCQ_DB_URL: str = os.getenv("JCQ_DB_URL", "sqlite:///./data/jcq.db")
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "jcq-authoring")

AUTHOR_MODEL: str = os.getenv("JCQ_AUTHOR_MODEL", "qwen2.5-coder:14b-instruct-q5_K_M")
VARIANT_COUNT: int = int(os.getenv("JCQ_VARIANT_COUNT", "5"))
MAX_AUTHOR_RETRIES: int = int(os.getenv("JCQ_AUTHOR_RETRIES", "2"))

JUDGE_PASS_THRESHOLD: float = float(os.getenv("JCQ_JUDGE_PASS_THRESHOLD", "0.7"))
SOLVER_PASS_MIN_AC: int = int(os.getenv("JCQ_SOLVER_PASS_MIN_AC", "1"))

# JCodeQuest/backend/ — storage·sandbox 재사용용
BACKEND_PATH: Path = Path(__file__).parent.parent.parent / "backend"


def ensure_backend_on_path() -> None:
    """backend/를 sys.path에 추가하고, JCQ_DB_URL이 미설정이면 절대경로 기본값을 주입한다.

    backend/src/storage/db.py는 모듈 임포트 시점에 os.getenv("JCQ_DB_URL")로 엔진을
    생성한다. 상대경로 기본값(sqlite:///./data/jcq.db)은 CWD에 따라 다른 파일을 가리키므로,
    첫 임포트 전에 환경변수를 절대경로로 확정해 두어야 한다.
    """
    import os

    bp = str(BACKEND_PATH)
    if bp not in sys.path:
        sys.path.insert(0, bp)

    if not os.environ.get("JCQ_DB_URL"):
        default_db = f"sqlite:///{BACKEND_PATH / 'data' / 'jcq.db'}"
        os.environ["JCQ_DB_URL"] = default_db
