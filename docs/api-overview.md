# API Overview — Swagger / OpenAPI

JCodeQuest의 두 서버(`backend`, `authoring_engine`)는 모두 **FastAPI** 기반이라, Swagger/OpenAPI 문서를 별도 코드 없이 자동 생성합니다. 본 저장소에서 별도 정적 문서가 필요한 경우 이 문서가 인덱스 역할을 합니다.

- [`api-backend.md`](api-backend.md) — 채점 서버 (포트 `8000`, 기본)
- [`api-authoring-engine.md`](api-authoring-engine.md) — 출제 엔진 서버 (포트 `8001`, 기본)

## 자동 생성된 Swagger / OpenAPI

서버를 실행하면 아래 경로가 즉시 사용 가능합니다.

| 서버 | OpenAPI JSON | Swagger UI | ReDoc |
| --- | --- | --- | --- |
| backend | `http://localhost:8000/openapi.json` | `http://localhost:8000/docs` | `http://localhost:8000/redoc` |
| authoring_engine | `http://localhost:8001/openapi.json` | `http://localhost:8001/docs` | `http://localhost:8001/redoc` |

### 띄우는 법

```bash
# 채점 서버
source backend/env.sh
cd backend && .venv/bin/uvicorn src.main:app --reload    # → :8000/docs

# 출제 엔진
cd authoring_engine && uvicorn authoring.server:app --port 8001
# → :8001/docs
```

> `backend/env.sh`는 gitignore되어 있고 `.env.example`이 템플릿입니다. 자세한 건 [`environment.md`](environment.md) 참조.

## 문서 동기화 정책

- **단일 진실 원천(SoT)은 코드 + Pydantic 스키마**입니다. `/openapi.json`이 항상 정답.
- `docs/api-*.md`는 사람이 빠르게 훑기 위한 요약 — 라우터/스키마가 바뀌면 같이 손봐야 합니다.
- 응답/요청 필드 정의는 다음 파일 참조:
  - 백엔드: `backend/src/schemas.py`, `shared/jcq_shared/schemas.py`
  - 출제 엔진: `authoring_engine/authoring/server.py` 내부의 `BaseModel` 클래스들

## 저장소에 커밋된 OpenAPI 명세

서버 없이도 명세를 열람·SDK 생성에 쓸 수 있도록 저장소에 정적 파일을 둡니다.

| 파일 | 출처 |
| --- | --- |
| [`openapi-backend.json`](openapi-backend.json) | `backend` FastAPI 앱의 `app.openapi()` |
| [`openapi-authoring.json`](openapi-authoring.json) | `authoring_engine` FastAPI 앱의 `app.openapi()` |

**`dev-login` 라우트는 prod-shape 명세에 포함하지 않습니다** (덤프 시 `JCQ_AUTH_ALLOW_DEV_STUB`를 비웁니다).

### 갱신 방법

라우터·Pydantic 스키마를 바꿨다면 아래 스크립트를 돌리고 결과를 함께 커밋합니다.

```bash
# 각 패키지 .venv 의존성이 분리되어 있어 한 번씩 호출
backend/.venv/bin/python           scripts/dump_openapi.py backend
authoring_engine/.venv/bin/python  scripts/dump_openapi.py authoring

# 한 인터프리터에 양쪽 패키지가 모두 설치된 환경(CI)이면 한 번에:
python scripts/dump_openapi.py both
```

### CI drift 체크

`.github/workflows/openapi.yml`이 PR마다 같은 스크립트를 돌려서 `git diff --exit-code`로 검사합니다. 라우터를 바꿨는데 `docs/openapi-*.json`을 같이 커밋하지 않으면 CI가 실패합니다. 따라서 로컬에서 갱신 → 커밋 → 푸시가 필수 절차.

### SDK 생성 (예시)

```bash
# TypeScript 타입
npx openapi-typescript docs/openapi-backend.json -o frontend/types/api.d.ts

# 다국어 클라이언트
openapi-generator-cli generate -i docs/openapi-backend.json -g python -o ./gen/py-client
```

## 인증 시 Swagger UI에서의 호출

`/docs`는 브라우저 쿠키를 그대로 사용하므로, **같은 origin/도메인에서 `/auth/login` → 콜백 완료 후 `/docs`를 열면** 인증 필요 엔드포인트도 그대로 호출됩니다. 로컬 개발에서는 `JCQ_AUTH_ALLOW_DEV_STUB=1` 후 `POST /auth/dev-login`을 한 번 호출하면 같은 쿠키 컨텍스트로 보호된 API를 시연할 수 있습니다(프로덕션 금지).
