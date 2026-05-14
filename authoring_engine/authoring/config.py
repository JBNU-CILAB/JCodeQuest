import os

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "jcq-authoring")

AUTHOR_MODEL: str = os.getenv("JCQ_AUTHOR_MODEL", "qwen2.5-coder:14b-instruct-q5_K_M")
VARIANT_COUNT: int = int(os.getenv("JCQ_VARIANT_COUNT", "5"))
MAX_AUTHOR_RETRIES: int = int(os.getenv("JCQ_AUTHOR_RETRIES", "2"))

JUDGE_PASS_THRESHOLD: float = float(os.getenv("JCQ_JUDGE_PASS_THRESHOLD", "0.7"))
SOLVER_PASS_MIN_AC: int = int(os.getenv("JCQ_SOLVER_PASS_MIN_AC", "1"))

# backend / judge_engine 내부 API. authoring은 더 이상 DB나 sandbox를 직접 다루지 않는다.
BACKEND_URL: str = os.getenv("JCQ_BACKEND_URL", "http://127.0.0.1:8000")
JUDGE_URL: str = os.getenv("JCQ_JUDGE_URL", "http://127.0.0.1:8002")
