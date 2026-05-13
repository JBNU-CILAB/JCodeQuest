# syntax=docker/dockerfile:1.7
# Build context: 모노레포 루트 (shared/ 가 ../shared 로 참조되기 때문)
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

# shared 먼저 — requirements.txt가 file:../shared로 참조
COPY shared/ /app/shared/
COPY backend/requirements.txt /app/backend/requirements.txt

WORKDIR /app/backend
RUN pip install -r requirements.txt

COPY backend/ /app/backend/

EXPOSE 8000

# init_db()로 새 DB 부트스트랩(있으면 no-op) → migrate.py로 incremental ALTER 적용 → uvicorn.
# JCQ_DB_URL은 compose에서 /data/jcq.db (마운트된 볼륨)로 주입.
CMD ["sh", "-c", "python -c 'from src.storage import init_db; init_db()' && python migrate.py && exec uvicorn src.main:app --host 0.0.0.0 --port 8000"]
