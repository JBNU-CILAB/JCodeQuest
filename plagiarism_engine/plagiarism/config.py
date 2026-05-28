"""환경변수 설정 — 모듈 로드 시 1회 읽음 (server.py가 load_dotenv 후 import)."""
import os
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "")


BACKEND_URL: str = os.getenv("JCQ_BACKEND_URL", "http://127.0.0.1:8000")
INTERNAL_SECRET: str = os.getenv("JCQ_INTERNAL_SECRET", "")

ENABLED: bool = _bool("JCQ_PLAGIARISM_ENABLED", True)
SIMILARITY_THRESHOLD: float = float(os.getenv("JCQ_PLAGIARISM_SIMILARITY_THRESHOLD", "0.7"))
TOP_K: int = int(os.getenv("JCQ_PLAGIARISM_TOP_K", "50"))
MIN_FRAGMENT: int = int(os.getenv("JCQ_PLAGIARISM_MIN_FRAGMENT", "10"))
INCLUDE_VERDICT: str = os.getenv("JCQ_PLAGIARISM_INCLUDE_VERDICT", "AC")
# 유사도 엔진: auto(Dolos 시도→실패 시 winnow 폴백) | dolos(강제) | winnow(강제, 의존성 0)
ENGINE: str = os.getenv("JCQ_PLAGIARISM_ENGINE", "auto").strip().lower()
LANGUAGE: str = os.getenv("JCQ_PLAGIARISM_LANGUAGE", "python")
MAX_CODE_BYTES: int = int(os.getenv("JCQ_PLAGIARISM_MAX_CODE_BYTES", str(64 * 1024)))
# Phase 2 멀티에이전트 판정 스위치 — 기본 off(Phase 1은 Dolos 단독).
ENSEMBLE_ENABLED: bool = _bool("JCQ_PLAGIARISM_ENSEMBLE_ENABLED", False)
# 판정 에이전트가 쓰는 모델/온도 (Ollama 기본; JCQ_LLM_PROVIDER=openai면 OpenAI로 스위치).
ENSEMBLE_MODEL: str = os.getenv("JCQ_PLAGIARISM_ENSEMBLE_MODEL", "qwen2.5-coder:14b-instruct-q5_K_M")
ENSEMBLE_TEMPERATURE: float = float(os.getenv("JCQ_PLAGIARISM_ENSEMBLE_TEMPERATURE", "0"))
ENSEMBLE_NUM_CTX: int = int(os.getenv("JCQ_PLAGIARISM_ENSEMBLE_NUM_CTX", "8192"))
# 판정 대상 상한 — 비용 통제(의심 쌍 중 상위 N개만 LLM 판정).
ADJUDICATE_TOP_N: int = int(os.getenv("JCQ_PLAGIARISM_ADJUDICATE_TOP_N", "20"))
# LLM이 코드를 분석할 때 잘라넣는 최대 길이(프롬프트 인젝션·토큰 통제).
AGENT_CODE_CHARS: int = int(os.getenv("JCQ_PLAGIARISM_AGENT_CODE_CHARS", "6000"))

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_KEEP_ALIVE: str = os.getenv("JCQ_OLLAMA_KEEP_ALIVE", "30m")

# Dolos Node 헬퍼
DOLOS_NODE: str = os.getenv("JCQ_DOLOS_NODE", "node")
DOLOS_SCRIPT: str = os.getenv(
    "JCQ_DOLOS_SCRIPT",
    str(Path(__file__).resolve().parent.parent / "dolos_runner" / "run_pairs.mjs"),
)
DOLOS_TIMEOUT_S: float = float(os.getenv("JCQ_DOLOS_TIMEOUT_S", "120"))

# 검출 파라미터 스냅샷 — run.config로 보존(사후 재현/감사용).
def snapshot() -> dict:
    return {
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "top_k": TOP_K,
        "min_fragment": MIN_FRAGMENT,
        "include_verdict": INCLUDE_VERDICT,
        "language": LANGUAGE,
        "engine": ENGINE,
        "ensemble_enabled": ENSEMBLE_ENABLED,
    }
