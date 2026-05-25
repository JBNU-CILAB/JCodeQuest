import os

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "jcq-authoring")

AUTHOR_MODEL: str = os.getenv("JCQ_AUTHOR_MODEL", "qwen2.5-coder:14b-instruct-q5_K_M")
VARIANT_COUNT: int = int(os.getenv("JCQ_VARIANT_COUNT", "5"))
MAX_AUTHOR_RETRIES: int = int(os.getenv("JCQ_AUTHOR_RETRIES", "2"))

# 출제 엔진 3-LLM 앙상블 모델. Melchior/Balthasar/Casper 세 판사가 solve_candidates(후보 풀이)와
# judge_candidates(품질 심사)에서 동일하게 쓰인다. compare 노드는 Melchior 단독으로 사용.
# 채점 엔진(judge_engine/judge/ensemble.py)의 동명 모델과는 별개로 독립 설정한다.
ENSEMBLE_MODEL_MELCHIOR: str = os.getenv(
    "JCQ_ENSEMBLE_MODEL_MELCHIOR", "qwen2.5-coder:14b-instruct-q5_K_M"
)
ENSEMBLE_MODEL_BALTHASAR: str = os.getenv(
    "JCQ_ENSEMBLE_MODEL_BALTHASAR", "deepseek-coder-v2:lite"
)
ENSEMBLE_MODEL_CASPER: str = os.getenv("JCQ_ENSEMBLE_MODEL_CASPER", "llama3.1:8b")

# (judge_id, model) 튜플 리스트 — solver/judge 노드가 그대로 순회한다.
ENSEMBLE_MODELS: list[tuple[str, str]] = [
    ("Melchior", ENSEMBLE_MODEL_MELCHIOR),
    ("Balthasar", ENSEMBLE_MODEL_BALTHASAR),
    ("Casper", ENSEMBLE_MODEL_CASPER),
]

# compare 노드는 단일 judge(Melchior)만 사용 — 비교 평가는 게이트가 아닌 순수 기록 목적.
COMPARE_MODEL: tuple[str, str] = ("Melchior", ENSEMBLE_MODEL_MELCHIOR)

# 3-LLM 앙상블(solve/judge/compare) context window. generate/verify의 AUTHOR_NUM_CTX와 별개.
# 긴 문제 statement+rubric에서 truncate를 피하려면 상향. 기본 8192.
ENSEMBLE_NUM_CTX: int = int(os.getenv("JCQ_ENSEMBLE_NUM_CTX", "8192"))

# Ollama keep_alive — 모델을 GPU 메모리에 유지하는 시간. 모든 ChatOllama 호출에 공통 적용.
# 모델을 자주 스왑하면 콜드 로드가 잦아지므로 충분히 길게 두는 게 처리량에 유리.
OLLAMA_KEEP_ALIVE: str = os.getenv("JCQ_OLLAMA_KEEP_ALIVE", "30m")

# generate(draft) 단계 temperature. 0이면 결정론적. 다양성을 원하면 상향.
AUTHOR_TEMPERATURE: float = float(os.getenv("JCQ_AUTHOR_TEMPERATURE", "0"))

# 앙상블(solve/judge/compare) temperature. 채점·심사는 결정론적이어야 하므로 기본 0.
ENSEMBLE_TEMPERATURE: float = float(os.getenv("JCQ_ENSEMBLE_TEMPERATURE", "0"))

# verify 단계에서 요구하는 최소 test_input 개수. 미만이면 후보를 폐기한다.
AUTHOR_MIN_TEST_CASES: int = int(os.getenv("JCQ_AUTHOR_MIN_TEST_CASES", "4"))

# solver가 풀이 LLM에 프롬프트로 노출하는 최대 샘플 케이스 수.
SOLVER_SAMPLE_LIMIT: int = int(os.getenv("JCQ_SOLVER_SAMPLE_LIMIT", "2"))

# 출제 LLM context window. 복잡한 문제는 statement+reference_code+test_inputs JSON이
# 길어져 기본 8192로는 truncate가 발생하므로 16384로 상향. qwen2.5-coder:14b는 32K까지.
AUTHOR_NUM_CTX: int = int(os.getenv("JCQ_AUTHOR_NUM_CTX", "16384"))

# verify 재시도 시 temperature. 0이면 결정론적이라 같은 실패를 반복하므로
# 재시도에선 다양성을 주기 위해 약간 올린다.
AUTHOR_RETRY_TEMPERATURE: float = float(os.getenv("JCQ_AUTHOR_RETRY_TEMPERATURE", "0.4"))

# reference_code가 time_limit_ms 대비 얼마나 빨라야 통과시키는지의 비율.
# 0.5는 너무 빡빡해 stress 케이스에서 자주 폐기되므로 0.8로 완화.
PERF_RATIO: float = float(os.getenv("JCQ_AUTHOR_PERF_RATIO", "0.8"))

JUDGE_PASS_THRESHOLD: float = float(os.getenv("JCQ_JUDGE_PASS_THRESHOLD", "0.7"))
SOLVER_PASS_MIN_AC: int = int(os.getenv("JCQ_SOLVER_PASS_MIN_AC", "1"))

# backend / judge_engine 내부 API. authoring은 더 이상 DB나 sandbox를 직접 다루지 않는다.
BACKEND_URL: str = os.getenv("JCQ_BACKEND_URL", "http://127.0.0.1:8000")
JUDGE_URL: str = os.getenv("JCQ_JUDGE_URL", "http://127.0.0.1:8002")
