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

# init_db()로 ORM 기준 테이블을 보장 (idempotent — Supabase에도 안전).
# migrate.py는 SQLite 한정 ALTER 스크립트이므로 postgres URL이면 스킵.
COPY backend/docker-entrypoint.sh /usr/local/bin/jcq-entrypoint.sh
RUN chmod +x /usr/local/bin/jcq-entrypoint.sh
CMD ["jcq-entrypoint.sh"]
