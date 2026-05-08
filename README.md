# JCodeQuest
Problem solving game for education.

전북대학교 SW경진대회 출품작 - JCodeQuest

## Project Summary
Algorithm Problem Solving을 Game처럼 즐길수 있는 플랫폼 - AI 자동 문제 출제 및 제출 시스템 사용. <br />
단계별 학습 코스 제공, 고도화 채점 시스템을 통한 정확한 채점 제공.

## Requirement
Python 3.14+, Ollama, FastAPI, LangChain, Docker(Linux) 필수. <br />

## Documents
- `docs/setup-ollama.md` — Backend Model Setup 가이드
- `docs/environment.md` — `backend/env.sh` 작성법, 환경변수 목록(필수/선택/테스트 전용)과 주의사항
- `docs/problem-format.md` — 문제·테스트케이스·채점 가이드(IntentRubric) 양식과 4축(자연성/부합성/복잡도/필수요소) 매핑
- `docs/authoring-prompt.md` — 출제 LangGraph의 `draft_problem` / `author_solution` 노드용 LLM 프롬프트 사양
- `docs/testing.md` — 테스트 계층(단위/통합/라이브/스모크), 실행 방법, 격리·LLM mocking 규약
