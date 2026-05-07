# JCodeQuest
Problem solving game for education.

전북대학교 SW경진대회 출품작 - JCodeQuest

## Project Summary
Algorithm Problem Solving을 Game처럼 즐길수 있는 플랫폼 - AI 자동 문제 출제 및 제출 시스템 사용. <br />
단계별 학습 코스 제공, 고도화 채점 시스템을 통한 정확한 채점 제공.

## Requirement
Python 3.14+, Ollama, FastAPI, LangChain, Docker(Linux) 필수. <br />
Backend Model Setup과 관련해서는 `docs/setup-ollama.md` 참조.

## Documents
- `docs/problem-format.md` — 문제·테스트케이스·채점 가이드(IntentRubric) 양식과 4축(자연성/부합성/복잡도/필수요소) 매핑
- `docs/authoring-prompt.md` — 출제 LangGraph의 `draft_problem` / `author_solution` 노드용 LLM 프롬프트 사양
