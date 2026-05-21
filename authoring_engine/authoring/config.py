import os

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "jcq-authoring")

AUTHOR_MODEL: str = os.getenv("JCQ_AUTHOR_MODEL", "qwen2.5-coder:14b-instruct-q5_K_M")
VARIANT_COUNT: int = int(os.getenv("JCQ_VARIANT_COUNT", "5"))
MAX_AUTHOR_RETRIES: int = int(os.getenv("JCQ_AUTHOR_RETRIES", "2"))

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
