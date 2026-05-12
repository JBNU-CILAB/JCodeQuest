# JCodeQuest
Problem solving game for education.

전북대학교 SW경진대회 출품작 - JCodeQuest

## Project Summary
Algorithm Problem Solving을 Game처럼 즐길수 있는 플랫폼 - AI 자동 문제 출제 및 제출 시스템 사용. <br />
단계별 학습 코스 제공, 고도화 채점 시스템을 통한 정확한 채점 제공.

## Requirement
Python 3.14+, Ollama, FastAPI, LangChain, Docker(Linux) 필수. <br />

## Quick Start — 로컬 개발 서버 일괄 기동

`scripts/dev.sh`로 백엔드(:8000) + 출제 엔진(:8001) + 프론트엔드(:5500) 세 프로세스를 한 번에 띄울 수 있다. PID/로그는 `.dev-logs/`에 보관되며 깔끔하게 종료된다.

```bash
scripts/dev.sh up        # 기동 + 헬스체크
scripts/dev.sh status    # 떠 있는지 확인 (PID / 포트 / health)
scripts/dev.sh logs backend     # uvicorn 로그 tail -f
scripts/dev.sh logs authoring
scripts/dev.sh logs frontend
scripts/dev.sh restart   # down → up
scripts/dev.sh down      # 모두 종료
```

| 서비스 | 포트 | 헬스 | 비고 |
|--------|------|------|------|
| backend | 8000 | `/health` | 채점 + 학습용 학생 API. dev-login은 `JCQ_AUTH_ALLOW_DEV_STUB=1`일 때만 |
| authoring | 8001 | `/api/health` | 원본/변형 조회 + 출제 파이프라인 트리거 |
| frontend | 5500 | `/index.html` | 정적 HTML 한 장. 브라우저로 `http://localhost:5500` 접속 |

사전 조건:
- `backend/.env` — `SESSION_SECRET_KEY`, `JCQ_DB_URL`(절대경로), `OPENAI_API_KEY`, `OLLAMA_BASE_URL`. dev-login으로 채점까지 시연하려면 `JCQ_AUTH_ALLOW_DEV_STUB=1`, `JCQ_COOKIE_INSECURE=1` 추가. 자세히는 `docs/environment.md`.
- `authoring_engine/.env` — `JCQ_DB_URL`은 backend와 **동일 파일**. 자세히는 `docs/authoring-engine.md`.
- Ollama 인스턴스가 `OLLAMA_BASE_URL`에서 응답하고 3개 판사 모델이 pull 되어 있어야 채점·출제가 동작 (`docs/setup-ollama.md`).

`scripts/dev.sh up`이 같은 포트가 이미 사용 중이라고 실패하면 다른 프로세스를 종료하거나 `scripts/dev.sh down` 후 재시도.

## Documents
- `docs/setup-ollama.md` — Backend Model Setup 가이드
- `docs/environment.md` — `backend/env.sh` 작성법, 환경변수 목록(필수/선택/테스트 전용)과 주의사항
- `docs/problem-format.md` — 문제·테스트케이스·채점 가이드(IntentRubric) 양식과 4축(자연성/부합성/복잡도/필수요소) 매핑
- `docs/authoring-prompt.md` — 출제 LangGraph의 `draft_problem` / `author_solution` 노드용 LLM 프롬프트 사양
- `docs/authoring-engine.md` — 출제 엔진(CLI/HTTP) 실행 가이드, 환경변수, 단계별 결과 해석법
- `docs/testing.md` — 테스트 계층(단위/통합/라이브/스모크), 실행 방법, 격리·LLM mocking 규약
