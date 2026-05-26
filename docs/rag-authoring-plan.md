# 출제 엔진 RAG 구현 계획

> 기존 문제 DB를 retrieval 소스로 활용해, 출제 엔진(`authoring_engine`)의 변형 생성 품질을
> 작은(≤10B) 로컬 모델 환경에서 끌어올리기 위한 설계 문서.

## 0. 배경 / 동기

- 작은 모델의 병목은 **지식 공백**보다 **추론 깊이 · 지시 준수 · 긴 컨텍스트 처리 · 도구 호출 신뢰성**.
- RAG/문서/지식그래프는 *지식 공백*만 해결한다. 따라서 우선순위는
  **(1) 작업 쪼개기 → (2) 출력 강제 → (3) 검증 루프 → (4) few-shot → (5) RAG** 순.
- 출제 엔진은 **기존 문제 DB가 이미 구조화된 지식베이스**라 RAG 투입 가치가 가장 높은 지점.
- 판사 앙상블은 필요한 정보(문제·코드·테스트결과)가 이미 컨텍스트에 다 있어 RAG 효용이 낮음 →
  **이 문서의 범위는 출제 엔진에 한정.**

## 1. 핵심 발견 — 임베딩 인프라는 이미 8할 존재

| 요소 | 위치 | 비고 |
|---|---|---|
| 임베딩 모델 | `authoring_engine/authoring/config.py:76` | `bge-m3` (OllamaEmbeddings), 1024차원 |
| 벡터 저장 | `backend/src/storage/models.py:101` | `ProblemRow.embedding` (JSON 컬럼) |
| 유사도 계산 | `authoring_engine/authoring/embeddings.py:45-73` | `cosine()`, `max_similarity()` |
| 카테고리 임베딩 조회 | `GET /internal/problems/{id}/category-embeddings` | `(id, title, embedding)` 반환 |
| 현재 활용처 | `authoring_engine/authoring/pipeline/nodes/generate.py:176-241` | **novelty check (중복 회피)** |

### 현재는 "밀어내기"에만 사용 중

| | 현재 (novelty) | RAG가 추가하는 것 |
|---|---|---|
| 방향 | 기존 문제와 **멀어지게** (중복 회피) | 기존 문제를 **끌어와서** 근거로 (스타일·난이도 grounding) |
| 임베딩 | `bge-m3` | **동일 재사용** |
| 데이터 | category-embeddings | **동일 재사용** |

> 결론: RAG는 새 시스템이 아니라 **이미 있는 임베딩을 retrieval 방향으로 한 번 더 쓰는 것.**

## 2. ⚠️ 가장 중요한 설계 함정 — top-k 유사도는 여기선 독이다

일반 QA RAG는 "가장 유사한 top-k"가 정답이지만, **출제 생성 + novelty 제약**에선 정반대:

> 가장 유사한 문제를 예시로 보여주면 → 모델이 그걸 베낀다 → 중복 생성 →
> **자기 자신의 novelty check(임계값 0.88)에 스스로 걸린다.**

따라서 retrieval 목표는 "유사한 것"이 아니라 **"관련 있지만 서로 다양한 모범 사례"**.

### 검색 전략

```
1. 메타데이터 필터:  category = 원본, status = approved, level ≈ 목표(±1)
2. 앵커 쿼리:        원본 문제 embedding (주제 관련성 확보)
3. MMR 재정렬:       관련성 vs 다양성을 λ로 균형
4. 품질 가중:        authoring_meta.judge_score 높은 것 우대
```

### MMR (Maximal Marginal Relevance) — 기존 `cosine()`만으로 구현

```python
# embeddings.py 에 추가 — 기존 cosine() 재사용
def mmr_select(query_vec, pool, k=3, lam=0.5):
    """pool: [(id, vec, payload)]. 관련성(query)과 다양성(기선택)을 lam으로 균형."""
    selected, rest = [], list(pool)
    while rest and len(selected) < k:
        best, best_score = None, -1e9
        for item in rest:
            rel = cosine(query_vec, item[1])
            div = max((cosine(item[1], s[1]) for s in selected), default=0.0)
            score = lam * rel - (1 - lam) * div
            if score > best_score:
                best, best_score = item, score
        selected.append(best); rest.remove(best)
    return selected
```

- `lam=0.7` → 관련성 우선, `lam=0.3` → 다양성 우선.
- **출제엔 0.4~0.5 권장** (novelty와 충돌 최소화).

## 3. 작은 모델 맞춤 — statement 말고 rubric을 주입

작은 모델은 긴 컨텍스트에서 성능이 무너진다. 검색된 문제의 **전체 statement(길다)** 대신,
이미 있는 **`IntentRubric`(압축된 본질)**을 주입한다.

```
[참고 문제 #N]  (예시 — 베끼지 말고 형식·난이도 참고)
- 제목: {title}
- 한줄: {one_line_summary}
- 접근: {expected_approach}
- 핵심: {key_insight}
- 복잡도: {expected_complexity}
```

- 문제당 ~5줄, 3개 넣어도 ~15줄 → `num_ctx=16384`에 부담 없음.
- 모델이 **구조만 배우고 내용은 베끼지 않게** 됨.
- `IntentRubric`이 RAG용 압축 표현으로 완벽 (4축: expected_approach / key_insight /
  expected_complexity / must_handle / forbidden_patterns + one_line_summary).

## 4. 아키텍처 (데이터 흐름)

```
fetch_problem ──┬─→ (기존) 원본 + sibling embeddings
                │
                └─→ [신규] retrieve_exemplars
                        │  1. category-embeddings 조회 (기존 엔드포인트)
                        │  2. level 필터 + MMR로 top-3 id 선정
                        │  3. 그 3개만 full rubric hydrate
                        ▼
generate_variants ──→ DRAFT_USER 에 exemplar 블록 주입
                      (기존 "3 seed" 자리를 retrieval 결과로 교체)
                      ↓ novelty check (그대로 유지)
verify → judge → solve → compare → persist
```

> 생성 흐름은 그대로 두고 **"어떤 예시를 보여줄지"만 똑똑하게** 바꾼다.

## 5. 구체적 변경점 (파일별, 최소 변경)

1. **`authoring_engine/authoring/embeddings.py`**
   - `mmr_select()` 추가 (2절 코드). 기존 `cosine()` 재사용.

2. **백엔드 엔드포인트** (`backend/src/storage/problems.py`, `backend/src/api/internal.py`)
   - `list_category_embeddings`가 현재 `(id, title, embedding)`만 반환 →
     **`level`, `judge_score` 추가** (컬럼에 이미 있어 거의 공짜).
   - top-3 선정 후 **full rubric hydrate**: 기존 `GET /internal/problems/{id}` 3회 호출,
     또는 배치 엔드포인트 신설(페이로드 최소화).

3. **`authoring_engine/authoring/pipeline/nodes/retrieve.py` (신규)**
   - 또는 `fetch.py`에 병합. MMR로 exemplar 선정 → state에 `exemplars: list[dict]` 저장.

4. **`authoring_engine/authoring/pipeline/graph.py`**
   - `fetch → retrieve → generate` 엣지 추가 (사실상 1줄).

5. **`authoring_engine/authoring/pipeline/prompts.py`**
   - `DRAFT_USER`의 seed 주입부를 3절 rubric 블록 포맷으로 교체.

6. **`authoring_engine/authoring/schemas.py` (AuthoringState)**
   - `exemplars` 필드 추가.

## 6. 저장소 결정 — JSON 유지, pgvector 보류

- 현재 brute-force 코사인(파이썬)으로 충분.
  - 문제 수가 **수천 개 이하**면 카테고리당 수십~수백 벡터 → 파이썬 루프 ms 단위.
- **pgvector 승격 시점**: 카테고리당 벡터 ~1만 개 초과 또는 retrieval 지연 체감 시.
  - 그때 `embedding JSONB → vector(1024)` 마이그레이션 (bge-m3 = 1024차원), ivfflat 인덱스.
- 지금 도입하면 `ALTER TABLE` + 확장 설치 + 인덱스 관리 비용만 늘고 이득 없음.
  - **"필요가 증명되기 전엔 인프라 만들지 않는다" 원칙.**
- 지식그래프는 구축·유지 비용이 과도 → **현 단계 보류.**

## 7. 가드레일

- **중복 방지 일관성**: retrieval λ를 너무 높이면(>0.7) novelty check와 충돌.
  0.4~0.5로 시작해 **novelty 재시도율** 보면서 튜닝.
- **빈 코퍼스 fail-open**: 신규 카테고리는 exemplar 0개 → 예시 없이 생성하는 현재 동작으로 폴백
  (novelty가 fail-open인 것과 동일).
- **품질 오염 방지**: `status=approved`만 검색 (draft/retired 제외).
  필요시 `judge_score` 임계값 추가.

## 8. 롤아웃 순서 (제안)

1. `mmr_select()` 추가 + 단위 테스트 (관련성/다양성 균형 확인).
2. `list_category_embeddings`에 `level`, `judge_score` 필드 추가.
3. `retrieve` 노드 + `graph.py` 엣지 + `AuthoringState.exemplars`.
4. `DRAFT_USER` 프롬프트에 rubric 블록 주입.
5. **A/B 측정**: RAG on/off로 (a) novelty 통과율 (b) judge_score (c) 중복률 비교.
6. λ · top-k(2~4) · level 윈도(±1) 튜닝.

## 9. 측정 지표

| 지표 | 의미 | 기대 방향 |
|---|---|---|
| novelty 통과율 | 첫 시도에 중복 안 걸리는 비율 | ↑ (예시가 형식만 주고 내용 안 베낌) |
| judge_score 평균 | 생성 변형 품질 | ↑ |
| novelty 재시도 횟수 | λ 과대 시 증가 | 안정 유지 |
| 생성 지연 | retrieval 오버헤드 | 무시 가능 수준 유지 |

---

### 부록 — 관련 스키마 참조

- `shared/jcq_shared/schemas.py`: `Problem`, `IntentRubric`(4축), `TestCase`
- `ProblemRow` 주요 컬럼: `embedding`(JSON), `intent_rubric`(JSON), `parent_id`(self-FK),
  `authoring_meta`(JSON, `judge_score` 포함), `status`(draft|approved|retired)
- 임베딩 텍스트 구성: `embeddings.py:problem_text()` (title + statement + expected_approach + key_insight)
