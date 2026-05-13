# syntax=docker/dockerfile:1.7
# authoring_engine은 backend/src/storage를 sys.path injection으로 import하므로
# 컨테이너에서도 backend/와 authoring_engine/이 같은 부모(/app) 아래 형제로 놓여야 한다.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade "pip>=23.1"

COPY shared/ /app/shared/
COPY authoring_engine/ /app/authoring_engine/

# authoring이 import하는 backend/src 모듈 — storage / schemas 등.
# requirements 설치는 하지 않고 소스만 둔다 (authoring의 의존성으로 충분).
COPY backend/src /app/backend/src

WORKDIR /app/authoring_engine
RUN pip install -e .

EXPOSE 8001

CMD ["uvicorn", "authoring.server:app", "--host", "0.0.0.0", "--port", "8001"]
