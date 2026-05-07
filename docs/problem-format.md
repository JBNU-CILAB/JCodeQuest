# 문제 양식 (Problem Format)

JCodeQuest의 모든 문제는 이 스키마를 따른다. 손으로 적든 출제 LLM이 자동 생성하든 동일한 형식이 채점 파이프라인에 들어간다.

진실값(source of truth)은 `backend/src/schemas.py`의 Pydantic 모델
(`Problem`, `IntentRubric`, `TestCase`). 이 문서는 그 모델의 의도를 풀어 쓴 출제·검수 가이드.

---

## 1. 전체 구조

```json
{
  "title": "팩토리얼",
  "statement": "정수 n (0 ≤ n ≤ 12)이 입력되면 n!을 출력하라.",
  "category": "basic",
  "level": "bronze",
  "points": 100,
  "time_limit_ms": 1000,
  "memory_limit_mb": 128,
  "reference_code": "n = int(input())\nr = 1\nfor i in range(1, n+1):\n    r *= i\nprint(r)\n",
  "intent_rubric": { /* §3 */ },
  "test_cases": [ /* §2 */ ]
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `title` | string | 사용자 UI에 보일 짧은 제목 |
| `statement` | string (markdown) | 문제 서술. 입출력 형식·제약을 포함 |
| `category` | string | 알고리즘 분류 (`dp`, `bfs`, `greedy`, `basic` …) |
| `level` | enum | `bronze` / `silver` / `gold` |
| `points` | int | AC 시 만점 (효율성 패널티 곱해진 후 부여) |
| `time_limit_ms` | int | 케이스당 wall-clock 상한 |
| `memory_limit_mb` | int | RLIMIT_AS 상한 |
| `reference_code` | string | 출제자/출제 LLM이 작성한 Python 정답. 검증과 expected_stdout 산출에 사용 |
| `intent_rubric` | object | 채점 시 LLM 판사가 참조할 출제자 의도 명세 (§3) |
| `test_cases` | array | 채점용 테스트 케이스 (§2) |

---

## 2. TestCase 양식

```json
{
  "ordinal": 1,
  "stdin": "5\n",
  "expected_stdout": "120",
  "is_sample": false
}
```

| 필드 | 의미 |
|---|---|
| `ordinal` | 1부터 시작하는 케이스 순번. 채점 결과에 그대로 표시 |
| `stdin` | 사용자 코드의 표준입력. 마지막 개행 포함 |
| `expected_stdout` | 기대 출력. **출제 시 LLM이 추측하지 말고 `reference_code`를 sandbox에 실제 실행해 얻은 값을 채울 것**. 비교는 양쪽 `rstrip()` |
| `is_sample` | true면 학생에게 stdin/expected를 노출 (문제 페이지). false면 hidden |

### 권장 분포 (PoC 기준)

- 케이스 수: **3 ~ 5개**
- `is_sample=true`: 1 ~ 2개
- 가능한 한 다음 종류 모두 포함:
  - **경계**: `intent_rubric.must_handle`에 적은 모든 항목과 1:1 대응되는 케이스
  - **일반**: 평이한 입력 1 ~ 2개
  - **스트레스**: 시간복잡도 한계를 자극하는 큰 입력 — `reference_code` 기준 `time_limit_ms`의 **30 ~ 70%**에서 통과해야 함 (학생 풀이의 여유 확보)

---

## 3. IntentRubric — 채점 가이드 양식

학생 코드가 모든 테스트를 통과해도 의도를 위배하면 SUS로 떨어져야 한다 (예: `if n==5: print(120) elif ...` 식의 정답 매핑). 그 판단을 LLM 판사 3명이 일관되게 내리도록, 출제 시점에 의도를 **4개 축**으로 명시한다.

### 3.1 4축 → 필드 매핑

| 축 | 의도 | 매핑 필드 | 작성 형식 |
|---|---|---|---|
| **자연성** | 사람이 자연스럽게 떠올리는 풀이 흐름 | `expected_approach` | 사고 흐름 1 ~ 2문장 |
| **부합성** | 어느 알고리즘 부류로 풀어야 하는가 — 핵심 통찰 | `key_insight` | 알고리즘의 핵심 1문장 |
| **복잡도** | 점근적 비용의 기대치 | `expected_complexity` | 빅오 표기 |
| **필수요소 (포함)** | 정답 코드가 반드시 다뤄야 할 입력/엣지 | `must_handle` | 짧은 항목 리스트 |
| **필수요소 (배제)** | 의도 위배 패턴 — LLM이 검출해야 할 안티패턴 | `forbidden_patterns` | **구체적인** 항목 리스트 |
| 메타 | 검색·UI 라벨 | `one_line_summary` | 한 줄 |

### 3.2 자연성 — `expected_approach`

이 문제에 대해 사람이 자연스럽게 떠올릴 풀이 흐름. "트릭이 아닌 정공법"이 무엇인지 서술. 부재 시 LLM은 "독창적이지만 의도 위배"인 풀이를 어떻게 평가할지 기준이 흔들린다.

**좋은 예**: `"1부터 n까지 누적 곱 (또는 재귀로 동등)"`

**나쁜 예**: `"팩토리얼을 계산"` — 너무 추상적, 풀이 흐름이 없음

### 3.3 부합성 — `key_insight`

해당 알고리즘 부류의 핵심 통찰 한 줄. 학생 코드를 LLM이 봤을 때 "이 통찰을 표현하고 있는가"를 검증하는 잣대.

**좋은 예**: `"0! = 1, n! = n × (n-1)!"`

**나쁜 예**: `"수학적 정의 사용"` — 통찰이 아니라 일반론

### 3.4 복잡도 — `expected_complexity`

빅오 표기. 통과는 가능하지만 의도와 멀어지는 풀이를 가려내는 데 쓰임 (예: O(n) 기대 문제에 O(n²) DP).

**예**: `"O(n)"`, `"O(n log n)"`, `"O(n × W)"`

### 3.5 필수요소 — `must_handle`

`reference_code`가 명시적으로 다뤄야 할 케이스. **테스트 케이스와 1:1 매칭**시키는 게 안전하다 (=각 항목당 적어도 한 케이스).

**예**: `["0! = 1", "1! = 1", "12! = 479001600"]`

### 3.6 필수요소 — `forbidden_patterns`

"테스트는 통과하지만 의도 위배"의 후보들. **이 리스트가 LLM 판사에게 가장 강한 시그널**이 된다. 추상적이면 검출률이 떨어진다.

| 추상적 (검출률 낮음) | 구체적 (검출률 높음) |
|---|---|
| "하드코딩 금지" | "if/elif로 입력값에 정답을 직접 매핑" |
| "트릭 금지" | "특정 테스트 입력만 처리하는 분기" |
| "효율 위반" | "O(n²) 이상의 이중 루프로 누적합 계산" |

**예**: `["하드코딩된 if/elif 분기로 특정 입력값에 정답 매핑", "특정 테스트 입력만 처리하는 분기"]`

### 3.7 메타 — `one_line_summary`

검색·분류·UI 라벨용 한 줄. 학생에게 보이는 부제 정도로 사용 가능.

**예**: `"팩토리얼 계산"`

### 3.8 (제안) 향후 확장 필드

현재 6 필드로도 4축 표현이 가능하나, 출제·채점 LLM이 더 일관되게 작동하도록 다음 필드 추가를 권장 (적용 시 schema 변경 필요):

```python
class IntentRubric(BaseModel):
    # ... 기존 필드 ...

    # 자연성 보강
    natural_alternative_approaches: list[str]   # 동등하게 자연스러운 다른 풀이들

    # 부합성 보강
    expected_algorithm_class: str               # "DP" / "그리디" / "BFS" 등 분류명
    forbidden_algorithms: list[str]             # 부적합/우회 알고리즘 부류

    # 복잡도 보강
    worst_acceptable_complexity: str            # 통과는 하지만 의도와 어긋날 가능성 있는 한계
```

채택 시기는 별도 결정. 우선은 6 필드 + 본 문서의 작성 규약으로 운용.

---

## 4. 검증 규칙 (status="approved" 진입 조건)

다음을 모두 만족해야 DB에 `status="approved"`로 저장된다 (실패 시 `status="draft"`로 보류 → 사람 검수 큐).

1. `reference_code`를 sandbox에서 모든 `test_cases`에 대해 실행 → **전부 PASS** (출제 그래프의 `verify_executes` 노드가 강제)
2. `reference_code`의 `max(elapsed_ms)`가 `time_limit_ms`의 **50% 이하** — 학생 풀이 여유 확보
3. `intent_rubric`의 모든 필드가 비어있지 않고, `must_handle`·`forbidden_patterns`는 각 1개 이상
4. `forbidden_patterns`의 모든 항목이 §3.6의 "구체적" 기준 충족 — 출제 그래프의 `judge_quality` 노드가 평가
5. (예정) statement 임베딩 cosine < 0.92 — 같은 카테고리의 다른 approved 문제와의 중복 차단

---

## 5. 완성 예시 — 팩토리얼

(`backend/tests/live/conftest.py:factorial_problem` 픽스처와 동일)

```json
{
  "title": "팩토리얼",
  "statement": "정수 n (0 ≤ n ≤ 12)이 입력되면 n!을 출력하라.",
  "category": "basic",
  "level": "bronze",
  "points": 100,
  "time_limit_ms": 1000,
  "memory_limit_mb": 128,
  "reference_code": "n = int(input())\nr = 1\nfor i in range(1, n + 1):\n    r *= i\nprint(r)\n",
  "intent_rubric": {
    "expected_approach": "1부터 n까지 누적 곱 (또는 재귀)",
    "expected_complexity": "O(n)",
    "must_handle": ["0! = 1", "1! = 1", "12! = 479001600"],
    "forbidden_patterns": [
      "하드코딩된 if/elif 분기로 특정 입력값에 정답 매핑",
      "특정 테스트 입력만 처리하는 분기"
    ],
    "key_insight": "0! = 1, n! = n × (n-1)!",
    "one_line_summary": "팩토리얼 계산"
  },
  "test_cases": [
    {"ordinal": 1, "stdin": "0\n",  "expected_stdout": "1",          "is_sample": true},
    {"ordinal": 2, "stdin": "1\n",  "expected_stdout": "1",          "is_sample": false},
    {"ordinal": 3, "stdin": "5\n",  "expected_stdout": "120",        "is_sample": false},
    {"ordinal": 4, "stdin": "12\n", "expected_stdout": "479001600",  "is_sample": false}
  ]
}
```

이 예시가 §4 검증 규칙을 모두 만족함을 확인하라:
- `reference_code` × 4 케이스 = 전부 PASS
- `must_handle` 3개 모두 테스트 케이스로 커버 (case 1, 2, 4)
- `forbidden_patterns`가 §3.6 기준대로 구체적 — `if/elif` 분기 명시
- `expected_complexity` 빅오 표기

이 문제로 SUS 후보를 던지면 (`if n==0: print(1); elif n==1: print(1); elif n==5: print(120); elif n==12: print(479001600)`), 의도상 LLM 판사들이 `forbidden_patterns` 첫 항목과 정확히 매칭해 SUS를 합의해야 한다. 합의가 안 되면 그 자체가 ensemble 약점 신호 — `tests/live/`의 `sus_hardcoded_factorial` 시나리오가 이 케이스를 측정한다.
