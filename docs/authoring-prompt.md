# 출제 프롬프트 (Authoring Prompts)

문제를 LLM이 자동 생성할 때 쓰는 프롬프트의 사양. `docs/problem-format.md`의 양식이 출력 계약(contract)이고, 이 문서는 그 계약을 만족하는 입력을 받기 위한 프롬프트 정의.

LangGraph 출제 그래프(`history.md` §5)의 두 노드에 각각 대응하는 프롬프트를 분리해서 정의한다:

| 노드 | 입력 | 출력 |
|---|---|---|
| `draft_problem` (§2) | seeds, category, level | `title`, `statement`, `intent_rubric` |
| `author_solution` (§3) | draft 결과 + category | `reference_code`, 각 케이스의 `stdin` 리스트 |

`expected_stdout`은 LLM이 만들지 않는다. `verify_executes` 노드가 `reference_code`를 sandbox에 실행해 산출 — 이게 환각 차단의 핵심.

운용 시점의 모델 라인업: `qwen2.5-coder:14b-instruct-q5_K_M` (생성 품질 우선, 출제 시점은 시간 압박 적음).

---

## 1. 공통 출력 규약

- 모든 응답은 **단일 JSON 객체**. 마크다운, 백틱, 코멘트 일절 금지.
- ChatOllama 호출 시 `format="json"` + `temperature=0` 고정.
- 한국어로 사용자 가시 필드(`title`, `statement`, rubric의 자연어 필드) 작성.
- `reference_code`는 Python 3.11+ 표준 라이브러리만 사용 (PoC 스코프).

---

## 2. `draft_problem` — 문제 서술 + 의도 명세

### 2.1 입력 변수

| 변수 | 의미 |
|---|---|
| `category` | 출제 카테고리 (`dp`, `bfs`, `greedy`, `basic` …) |
| `level` | `bronze` / `silver` / `gold` |
| `seeds` | 같은 카테고리의 기존 approved 문제 3개 (variant 다양성·중복 회피용) |
| `time_limit_ms`, `memory_limit_mb` | 출제자가 정한 한계 (출력에 그대로 echo) |

### 2.2 시스템 프롬프트

```
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
}
```

### 2.3 사용자 프롬프트 (템플릿)

```
[목표]
- category: {category}
- level: {level}
- time_limit_ms: {time_limit_ms}
- memory_limit_mb: {memory_limit_mb}

[같은 카테고리의 기존 문제 (seeds — 변형 시 흐름 겹침 회피)]
1. {seed_1.title} — {seed_1.intent_rubric.one_line_summary}
   접근: {seed_1.intent_rubric.expected_approach}
2. {seed_2.title} — {seed_2.intent_rubric.one_line_summary}
   접근: {seed_2.intent_rubric.expected_approach}
3. {seed_3.title} — {seed_3.intent_rubric.one_line_summary}
   접근: {seed_3.intent_rubric.expected_approach}

위 seeds와 충분히 다른 새 문제 한 개를 위 시스템 규칙대로 설계하라.
JSON으로만 응답.
```

### 2.4 출력 계약

| 필드 | 검증 |
|---|---|
| `title` | 비어있지 않음, ≤ 60자 |
| `statement` | ≥ 50자, 입출력 형식 언급 |
| `intent_rubric.*` | 모든 6 필드 비어있지 않음 |
| `must_handle` | ≥ 1개 |
| `forbidden_patterns` | ≥ 1개, 각 항목이 추상어("하드코딩", "트릭") 단독으로 끝나지 않음 |

검증 실패 시 → `judge_quality`가 `status="draft"`로 보류 후 사람 검수 큐.

---

## 3. `author_solution` — 정답 코드 + 테스트 입력

### 3.1 입력 변수

| 변수 | 의미 |
|---|---|
| `draft` | §2의 출력 (title, statement, intent_rubric) |
| `category` | echo |
| `time_limit_ms`, `memory_limit_mb` | echo (참고용) |

### 3.2 시스템 프롬프트

```
당신은 위에서 출제된 문제의 정답 코드를 작성하고, 그 코드를 검증할
테스트 입력 셋을 생성한다.

규칙:

- reference_code는 Python 3.11+ 표준 라이브러리만 사용. 외부 패키지 금지.
- reference_code는 statement에 적힌 입출력 형식을 정확히 따른다 — stdin
  으로 받고 stdout으로 출력. 함수 정의만 하고 끝나면 안 된다.
- reference_code는 intent_rubric.expected_approach가 명시한 풀이 흐름을
  따라야 한다. 다른 알고리즘으로 우회하지 마라.
- reference_code는 intent_rubric.expected_complexity를 만족해야 한다.

테스트 입력 (stdin) 4~8개 생성:

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
}
```

### 3.3 사용자 프롬프트 (템플릿)

```
[문제]
제목: {draft.title}
서술: {draft.statement}

[의도 명세]
접근(자연성): {intent_rubric.expected_approach}
핵심 통찰(부합성): {intent_rubric.key_insight}
복잡도: {intent_rubric.expected_complexity}
반드시 처리(must_handle): {intent_rubric.must_handle}
금지 패턴(forbidden_patterns): {intent_rubric.forbidden_patterns}

[제약]
- time_limit_ms: {time_limit_ms}
- memory_limit_mb: {memory_limit_mb}

위 명세에 충실한 reference_code와 4~8개 stdin을 위 규칙대로 생성.
JSON으로만 응답.
```

### 3.4 출력 계약

| 필드 | 검증 |
|---|---|
| `reference_code` | 비어있지 않음, ≤ 4KB |
| `test_inputs` | 4 ~ 8개, ordinal이 1부터 연속, sample 1 ~ 2개 |

검증 실패 시 → `verify_executes` 노드의 자기루프 (max 2회 재시도) 트리거.

---

## 4. 후속 단계 (LLM 미관여)

§3의 출력이 들어오면 LangGraph는 다음을 LLM 호출 없이 처리:

1. `verify_executes`: `reference_code`를 각 `stdin`에 대해 sandbox 실행
   - 모두 `status="OK"`이고 `elapsed_ms ≤ time_limit_ms × 0.5` → 진행
   - 실패 시 → `author_solution`로 자기루프 (max 2회). 그래도 실패 시 `status="draft"`로 보류
   - 각 케이스의 `stdout`을 `expected_stdout`으로 박음
2. `judge_quality`: 3-judge ensemble이 problem 전체를 4축 기준으로 품질 투표 (별도 프롬프트, 본 문서 범위 밖)
3. `persist_final`: 임베딩 중복 체크 후 `status="approved"` 또는 `"draft"`로 저장

---

## 5. 운영상의 함정

- **`format="json"`이라도 LLM이 마크다운 펜스를 끼울 때가 있다** — 파싱 전에 `str.strip()` + 양 끝의 ```` ``` ```` 제거 후처리 필수.
- **stdin 끝의 개행** — 학생 코드의 `input()`이 EOF에서 깨지지 않도록 `\n`으로 끝나야 안전. 프롬프트에 명시했지만 후처리에서도 강제하는 게 좋다.
- **must_handle ↔ test_inputs 매칭** — 검증 단계에서 항목이 케이스로 커버됐는지 자동 확인이 어렵다. 1차로 LLM에 맡기되, `judge_quality` 프롬프트에서 "must_handle의 각 항목이 어느 stdin에서 검증되는가"를 묻는 후속 점검을 권장.
- **카테고리별 시드 부족** — 첫 부트스트랩 시 seeds가 2개 이하면 다양성 시그널이 약하다. `scripts/seed_demo.py`로 카테고리당 최소 3문제는 손으로 박고 시작.
