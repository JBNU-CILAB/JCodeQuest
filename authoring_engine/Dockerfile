# syntax=docker/dockerfile:1.7
# authoring_engine은 backend의 /internal/* HTTP API와 judge_engine의 /api/sandbox/run을
# 통해 동작한다. backend/src를 더 이상 import하지 않으므로 shared만 같이 끌어온다.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --upgrade "pip>=23.1"

COPY shared/ /app/shared/
COPY authoring_engine/ /app/authoring_engine/

WORKDIR /app/authoring_engine
RUN pip install -e .

EXPOSE 8001

CMD ["uvicorn", "authoring.server:app", "--host", "0.0.0.0", "--port", "8001"]
