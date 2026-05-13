# syntax=docker/dockerfile:1.7
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
COPY judge_engine/ /app/judge_engine/

WORKDIR /app/judge_engine
RUN pip install -e .

EXPOSE 8002

CMD ["uvicorn", "judge.server:app", "--host", "0.0.0.0", "--port", "8002"]
