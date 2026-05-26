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

# ─── judge 신뢰도/편향 개선 ────────────────────────────────────────────────
# 판사별 self-consistency 샘플 수. 1이면 기존 동작(단일 결정론적 호출). 2 이상이면
# JUDGE_SELFCONSIST_TEMP로 N회 샘플 후 판사 내에서 passed=다수결, score=중앙값으로 합산한다.
# 비용이 N배라 기본 1(off). 작은 모델의 점수 흔들림을 줄이고 싶을 때만 상향.
JUDGE_SAMPLES: int = int(os.getenv("JCQ_JUDGE_SAMPLES", "1"))
# self-consistency 샘플링 온도. 0이면 샘플이 전부 같아 의미가 없으므로 약간 올린다.
JUDGE_SELFCONSIST_TEMP: float = float(os.getenv("JCQ_JUDGE_SELFCONSIST_TEMP", "0.3"))

# ─── 변별력(테스트 강도) 검사 ──────────────────────────────────────────────
# solve_candidates가 '풀 수 있나'를 보는 반면, attack_candidates는 '틀린 풀이가
# hidden 테스트에 걸리나'를 본다. rubric(must_handle/forbidden_patterns/복잡도)을
# 표적으로 결함을 심은 공격 풀이 K개를 만들어 전체 test_cases에 돌린다.
DISCRIMINATION_ENABLED: bool = os.getenv("JCQ_DISCRIMINATION_ENABLED", "1").lower() not in (
    "0",
    "false",
    "no",
    "",
)
# 생성할 공격 풀이 수.
DISCRIMINATION_ATTACKS: int = int(os.getenv("JCQ_DISCRIMINATION_ATTACKS", "2"))
# 테스트가 최소 몇 개의 공격 풀이를 '탈락(non-AC)'시켜야 통과로 보는지. 기본 1 — 0개면
# 테스트가 어떤 결함도 못 걸러낸다는 뜻이라 폐기. (LLM 공격이 전부 실패하면 fail-open)
DISCRIMINATION_MIN_REJECT: int = int(os.getenv("JCQ_DISCRIMINATION_MIN_REJECT", "1"))

# ─── compare 게이트 승격 ──────────────────────────────────────────────────
# 기록만 하던 compare 3축 중 환각·의도유사도를 persist 게이트로 사용한다.
# difficulty_similarity는 변형이 난이도를 달리해도 무방하므로 게이트에서 제외(기록만).
# 단일 judge 결과라 fail-open: compare 오류 시 통과시켜 3-judge·solver·변별력을 모두
# 통과한 후보를 노이즈로 버리지 않는다.
COMPARE_GATE_ENABLED: bool = os.getenv("JCQ_COMPARE_GATE_ENABLED", "1").lower() not in (
    "0",
    "false",
    "no",
    "",
)
# 이 값을 초과하는 환각(hallucination_score)이면 폐기.
COMPARE_MAX_HALLUCINATION: float = float(os.getenv("JCQ_COMPARE_MAX_HALLUCINATION", "0.5"))
# 이 값 미만 의도유사도면 원본 카테고리 이탈로 보고 폐기.
COMPARE_MIN_INTENT_SIM: float = float(os.getenv("JCQ_COMPARE_MIN_INTENT_SIM", "0.4"))

# ─── 신규성(중복) 검사 ──────────────────────────────────────────────────────
# generate_variants가 각 변형 draft를 임베딩해 같은 카테고리 형제와 코사인 유사도를 비교,
# 임계 이상이면 겹침 피드백을 주고 재draft한다(최대 NOVELTY_MAX_RETRIES회). 비싼
# author_solution 이전에 거르므로 비용이 절약된다. 한국어 statement라 다국어 임베딩 권장.
NOVELTY_ENABLED: bool = os.getenv("JCQ_NOVELTY_ENABLED", "1").lower() not in (
    "0",
    "false",
    "no",
    "",
)
# Ollama 임베딩 모델 태그. 원격 서버에 `ollama pull <태그>`로 미리 받아둬야 한다.
EMBED_MODEL: str = os.getenv("JCQ_EMBED_MODEL", "bge-m3")
# 코사인 유사도 임계값. 이 값 이상이면 "너무 유사"로 보고 재생성을 유도. 튜닝 대상.
NOVELTY_THRESHOLD: float = float(os.getenv("JCQ_NOVELTY_THRESHOLD", "0.88"))
# 신규성 미달 시 draft 재시도 횟수(초기 1회 + 재시도 N회). 모두 실패하면 후보를 폐기.
NOVELTY_MAX_RETRIES: int = int(os.getenv("JCQ_NOVELTY_MAX_RETRIES", "2"))

# ─── RAG exemplar retrieval ──────────────────────────────────────────────────
# retrieve_exemplars 노드가 같은 카테고리 approved 문제 중 MMR로 "관련 있지만 서로 다른"
# 모범 사례를 골라 draft 프롬프트에 rubric 형태로 주입한다(전체 statement가 아니라
# IntentRubric 압축본 → 작은 모델 컨텍스트 부담 최소화). novelty와 반대 방향의 임베딩 사용.
# 임계/윈도/λ는 docs/rag-authoring-plan.md §6~8 참조. 빈 코퍼스/임베딩 실패는 fail-open.
RAG_ENABLED: bool = os.getenv("JCQ_RAG_ENABLED", "1").lower() not in (
    "0",
    "false",
    "no",
    "",
)
# exemplar 개수(top-k). 2~4 권장.
RAG_TOP_K: int = int(os.getenv("JCQ_RAG_TOP_K", "3"))
# MMR λ. 관련성 vs 다양성 균형. >0.7이면 novelty 검사와 충돌하므로 0.4~0.5로 시작.
RAG_MMR_LAMBDA: float = float(os.getenv("JCQ_RAG_MMR_LAMBDA", "0.5"))
# 레벨 윈도. 목표 레벨에서 ±N 단계(bronze<silver<gold)까지 exemplar 후보로 허용.
RAG_LEVEL_WINDOW: int = int(os.getenv("JCQ_RAG_LEVEL_WINDOW", "1"))
# 품질 게이트. judge_score가 이 값 미만인 형제는 exemplar에서 제외(0이면 비활성).
# judge_score가 None인(수기 출제 원본 등) 문제는 항상 통과시켜 양질의 원본을 살린다.
RAG_MIN_JUDGE_SCORE: float = float(os.getenv("JCQ_RAG_MIN_JUDGE_SCORE", "0"))

# backend / judge_engine 내부 API. authoring은 더 이상 DB나 sandbox를 직접 다루지 않는다.
BACKEND_URL: str = os.getenv("JCQ_BACKEND_URL", "http://127.0.0.1:8000")
JUDGE_URL: str = os.getenv("JCQ_JUDGE_URL", "http://127.0.0.1:8002")
