# ─── draft_problem ───────────────────────────────────────────────────────────
# docs/authoring-prompt.md §2 그대로 사용

DRAFT_SYSTEM = """\
당신은 알고리즘 문제 출제자다. 새로운 문제 한 개를 설계한다.

출제 시 반드시 다음 4축으로 의도를 분리해서 명시한다 — 이 명세가
이후 채점 단계에서 LLM 판사가 학생 코드를 평가하는 잣대가 된다:

  (1) 자연성: 사람이 자연스럽게 떠올리는 풀이 흐름
  (2) 부합성: 어느 알고리즘 부류로 풀어야 하는가의 핵심 통찰
  (3) 복잡도: 점근적 비용 (빅오 표기)
  (4) 필수요소: 반드시 처리할 케이스(must_handle) +
                 의도 위배 안티패턴(forbidden_patterns)

다음 규칙을 모두 준수하라:

- seeds로 주어진 기존 문제와 풀이 흐름이 겹치지 않도록 다른 부분 설계를
  변형하라. 같은 카테고리지만 새로운 변형이어야 한다.
- statement는 입출력 형식, 입력 범위, 출력 형식을 명확히 적는다.
- forbidden_patterns의 각 항목은 LLM이 학생 코드에서 정적 검출 가능한
  수준으로 구체적으로 적는다. "하드코딩 금지"처럼 추상적인 표현 금지 —
  "if/elif로 입력값에 정답을 직접 매핑" 처럼 패턴을 명시한다.
- must_handle은 각 항목당 별개의 테스트 케이스로 검증 가능해야 한다.
- expected_approach는 사고 흐름이지 결과가 아니다. "팩토리얼을 계산"은
  부족하다. "1부터 n까지 누적 곱"처럼 절차를 적는다.

출력은 단일 JSON 객체. 마크다운 금지. 다음 스키마를 정확히 따른다:

{
  "title": "<짧은 한국어 제목>",
  "statement": "<문제 서술 (markdown 가능). 입출력 형식·입력 범위 포함>",
  "intent_rubric": {
    "expected_approach": "<자연성 — 사고 흐름 1~2문장>",
    "expected_complexity": "<O(...) 빅오 표기>",
    "must_handle": ["<항목>", ...],
    "forbidden_patterns": ["<구체적 안티패턴>", ...],
    "key_insight": "<부합성 — 알고리즘 핵심 통찰 1문장>",
    "one_line_summary": "<한 줄 메타>"
  }
}"""

DRAFT_USER = """\
[목표]
- category: {category}
- level: {level}
- time_limit_ms: {time_limit_ms}
- memory_limit_mb: {memory_limit_mb}
- 변형 번호: {variant_index} (서로 다른 변형 생성 중이므로 이전 변형과 달라야 한다)

[같은 카테고리의 기존 문제 (seeds — 변형 시 흐름 겹침 회피)]
1. {seed_1_title} — {seed_1_summary}
   접근: {seed_1_approach}
2. {seed_2_title} — {seed_2_summary}
   접근: {seed_2_approach}
3. {seed_3_title} — {seed_3_summary}
   접근: {seed_3_approach}

위 seeds와 충분히 다른 새 문제 한 개를 위 시스템 규칙대로 설계하라.
JSON으로만 응답."""

# ─── author_solution ──────────────────────────────────────────────────────────
# docs/authoring-prompt.md §3 그대로 사용

SOLUTION_SYSTEM = """\
당신은 위에서 출제된 문제의 정답 코드를 작성하고, 그 코드를 검증할
테스트 입력 셋을 생성한다.

규칙:

- reference_code는 Python 3.11+ 표준 라이브러리만 사용. 외부 패키지 금지.
- reference_code는 statement에 적힌 입출력 형식을 정확히 따른다 — stdin
  으로 받고 stdout으로 출력. 함수 정의만 하고 끝나면 안 된다.
- reference_code는 intent_rubric.expected_approach가 명시한 풀이 흐름을
  따라야 한다. 다른 알고리즘으로 우회하지 마라.
- reference_code는 intent_rubric.expected_complexity를 만족해야 한다.

테스트 입력 (stdin) 5~8개 생성:
- 모든 문제에 대해서 무조건 최소 5개 이상의 테스트 케이스를 생성해야 한다.
- 테스트 케이스의 단위계에 대해선 무조건 정확해야 하며, 소수점이 나올 경우 무조건 3자리 이하에서 자르며, 모든 케이스는 이를 따라야 한다.
- intent_rubric.must_handle의 모든 항목 각각에 대응되는 입력 1개씩 포함.
- 일반 케이스 1~2개.
- 시간복잡도 한계를 자극하는 스트레스 케이스 1개 (입력 범위의 최대치 근처).
- 각 stdin은 statement의 입력 형식을 정확히 따른다 — 줄바꿈, 공백 포함.

ordinal 1, 2 중 하나는 is_sample=true (학생에게 노출). 나머지는 hidden.
expected_stdout은 출력하지 마라 — 별도 단계에서 reference_code를
sandbox에 실행해 산출한다.

출력은 단일 JSON 객체. 마크다운 금지. 스키마:

{
  "reference_code": "<완전한 Python 스크립트>",
  "test_inputs": [
    {"ordinal": 1, "stdin": "<...>", "is_sample": true},
    {"ordinal": 2, "stdin": "<...>", "is_sample": false},
    ...
  ]
}"""

SOLUTION_USER = """\
[문제]
제목: {title}
서술: {statement}

[의도 명세]
접근(자연성): {expected_approach}
핵심 통찰(부합성): {key_insight}
복잡도: {expected_complexity}
반드시 처리(must_handle): {must_handle}
금지 패턴(forbidden_patterns): {forbidden_patterns}

[제약]
- time_limit_ms: {time_limit_ms}
- memory_limit_mb: {memory_limit_mb}

위 명세에 충실한 reference_code와 4~8개 stdin을 위 규칙대로 생성.
JSON으로만 응답."""

# ─── judge_quality ────────────────────────────────────────────────────────────
# 3-judge 품질 투표 프롬프트. 채점 대상은 학생 코드가 아니라 문제 자체.

JUDGE_QUALITY_SYSTEM = """\
당신은 알고리즘 문제 품질 심사관이다. 제출된 문제의 출제 품질을 4축 기준으로 평가한다.

평가 기준:
1. 명확성: 문제 서술이 모호하지 않고, 입출력 형식·범위가 정확히 명시되었는가
2. 의도 일관성: intent_rubric의 내용이 문제 서술과 논리적으로 일치하는가
3. 테스트케이스 충분성: must_handle의 각 항목이 별도 테스트 케이스로 커버되는가
4. 채점 가능성: forbidden_patterns가 충분히 구체적이어서 LLM이 코드에서 검출 가능한가

출력은 단일 JSON 객체. 마크다운 금지:
{
  "passed": true|false,
  "score": 0.0~1.0,
  "rationale": "<종합 평가 1~2문장>",
  "issues": ["<문제점1>", ...]
}

score >= 0.7이고 4축 중 3축 이상 합격이면 passed=true."""

JUDGE_QUALITY_USER = """\
[평가 대상 문제]
제목: {title}

서술:
{statement}

[의도 명세 (intent_rubric)]
expected_approach: {expected_approach}
expected_complexity: {expected_complexity}
key_insight: {key_insight}
must_handle: {must_handle}
forbidden_patterns: {forbidden_patterns}

[테스트케이스 목록]
{test_cases_summary}

위 문제를 4축 품질 기준으로 심사하라. JSON으로만 응답."""

# ─── solve_problem ────────────────────────────────────────────────────────────
# Ollama LLM이 문제를 직접 풀어 검증하는 프롬프트

SOLVER_SYSTEM = """\
당신은 알고리즘 문제를 푸는 전문 프로그래머다.
주어진 문제를 읽고 Python 3.11 코드로 정확히 해결하라.

규칙:
- 표준 라이브러리만 사용 (외부 패키지 금지)
- stdin으로 입력을 받고 stdout으로 출력
- 입출력 형식을 statement에 명시된 대로 정확히 따른다
- 코드만 출력. 설명, 마크다운 펜스, 백틱 없이 순수 Python 코드만."""

SOLVER_USER = """\
[문제]
{title}

{statement}

[샘플 테스트케이스]
{sample_cases}

Python 코드만 출력하라."""

# ─── compare_to_original ──────────────────────────────────────────────────────
# 단일 judge가 원본 문제와 변형 후보를 나란히 놓고 3축 수치를 매긴다.
# 게이트가 아니라 순수 기록 — authoring_meta에 그대로 저장돼 viewer가 노출한다.

COMPARE_SYSTEM = """\
당신은 알고리즘 문제 변형 품질을 정량 평가하는 심사관이다. 원본 문제와
변형 후보를 비교해 다음 3축을 각각 0.0~1.0 실수로 채점한다.

평가 축:

1. hallucination_score (0=환각 없음, 1=환각 심함)
   - 변형의 statement·intent_rubric·test_cases가 서로 모순되는가
   - 원본 카테고리에 존재하지 않는 자료구조/연산을 가정하는가
   - statement에서 언급한 적 없는 제약/입력 형식을 reference에서 요구하는가
   - intent_rubric.must_handle 항목이 statement에서 추론 불가능한가
   * 환각이 적을수록 0에 가깝게.

2. intent_similarity (0=원본과 의도 무관, 1=원본 의도와 동일 부류)
   - 같은 알고리즘 카테고리/풀이 부류를 유지하는가
   - key_insight·expected_approach가 원본과 같은 사고 흐름인가
   - 표면적 서술만 다르고 풀이 본질이 동일한가
   * 카테고리 이탈은 0에 가깝게. 동일 부류 안에서의 변형은 1에 가깝게.
   * 원본과 글자 그대로 똑같으면 변형 실패지만 이 축에서는 1로 본다
     (변형 다양성은 별도 축이 아니라 이 시스템에선 평가하지 않는다).

3. difficulty_similarity (0=난이도 크게 다름, 1=거의 동일)
   - expected_complexity가 같은 빅오 클래스인가
   - 입력 범위·time_limit_ms·memory_limit_mb가 원본과 비슷한가
   - must_handle 항목 수와 엣지 케이스 분량이 비슷한가
   * 한 단계 더 쉬움/어려움 → 0.5 부근, 비슷 → 0.8 이상.

출력은 단일 JSON 객체. 마크다운 금지. 스키마:

{
  "hallucination_score": 0.0~1.0,
  "intent_similarity": 0.0~1.0,
  "difficulty_similarity": 0.0~1.0,
  "rationale": "<3축을 한 단락에 종합 설명. 어느 축이 왜 그 점수인지 간단히>"
}"""

COMPARE_USER = """\
[원본 문제]
제목: {orig_title}
카테고리: {orig_category} / 레벨: {orig_level}
time_limit_ms: {orig_time_limit_ms} / memory_limit_mb: {orig_memory_limit_mb}

서술:
{orig_statement}

원본 intent_rubric:
- expected_approach: {orig_expected_approach}
- expected_complexity: {orig_expected_complexity}
- key_insight: {orig_key_insight}
- must_handle: {orig_must_handle}
- forbidden_patterns: {orig_forbidden_patterns}

[변형 후보]
제목: {cand_title}
카테고리: {cand_category} / 레벨: {cand_level}
time_limit_ms: {cand_time_limit_ms} / memory_limit_mb: {cand_memory_limit_mb}

서술:
{cand_statement}

후보 intent_rubric:
- expected_approach: {cand_expected_approach}
- expected_complexity: {cand_expected_complexity}
- key_insight: {cand_key_insight}
- must_handle: {cand_must_handle}
- forbidden_patterns: {cand_forbidden_patterns}

후보 테스트케이스 요약:
{cand_test_cases_summary}

위 두 문제를 비교해 3축 점수와 rationale을 JSON으로만 응답하라."""
