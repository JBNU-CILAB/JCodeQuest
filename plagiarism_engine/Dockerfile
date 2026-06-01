# syntax=docker/dockerfile:1.7
# plagiarism_engine: Python(FastAPI) + Node(Dolos AST 유사도 엔진).
# Dolos는 tree-sitter 네이티브 바인딩이 필요해 빌드 시 g++/make + node-gyp가 동원된다.
# 레이어 순서: apt → pip → dolos package*.json 먼저 → npm ci → 나머지 코드 → pip install.
# (dolos package-lock이 안 바뀌면 npm ci 레이어가 캐시 hit해 재빌드가 빠르다.)
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false \
    # node-gyp가 native 빌드 시 `python` 명령을 찾는데 slim 이미지엔 심볼릭이 없으므로 명시.
    NPM_CONFIG_PYTHON=/usr/local/bin/python3

WORKDIR /app

RUN pip install --upgrade "pip>=23.1"

# Dolos Node 러너 의존성 — package*.json만 먼저 복사해 npm ci 레이어가
# 파이썬 코드 변경에 흔들리지 않게 한다(캐시 효율).
COPY plagiarism_engine/dolos_runner/package.json \
     plagiarism_engine/dolos_runner/package-lock.json \
     /app/plagiarism_engine/dolos_runner/
WORKDIR /app/plagiarism_engine/dolos_runner
RUN npm ci --omit=dev

# 나머지 코드 (shared + plagiarism_engine 본체).
# .dockerignore가 **/node_modules/를 제외하므로 위에서 설치한 node_modules는 살아남는다.
COPY shared/ /app/shared/
COPY plagiarism_engine/ /app/plagiarism_engine/

WORKDIR /app/plagiarism_engine
RUN pip install -e .

EXPOSE 8003

# Dolos 동작 확인용 헬스 로그 — 컨테이너 시작 직후 node와 러너 진입점이 보이는지 stderr에 한 줄.
CMD ["sh", "-c", "node --version >&2 && ls /app/plagiarism_engine/dolos_runner/run_pairs.mjs >&2 && exec uvicorn plagiarism.server:app --host 0.0.0.0 --port 8003"]
