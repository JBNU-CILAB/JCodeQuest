# syntax=docker/dockerfile:1.7
# plagiarism_engine은 backend의 /internal/* HTTP API로만 동작한다(DB 직접 참조 없음).
# 기본 유사도 엔진은 winnow(순수 Python) — 이 이미지엔 Node가 없다.
# Dolos를 쓰려면 node + dolos_runner npm install 레이어를 추가하고 JCQ_PLAGIARISM_ENGINE=auto/dolos로.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --upgrade "pip>=23.1"

COPY shared/ /app/shared/
COPY plagiarism_engine/ /app/plagiarism_engine/

WORKDIR /app/plagiarism_engine
RUN pip install -e .

EXPOSE 8003

CMD ["uvicorn", "plagiarism.server:app", "--host", "0.0.0.0", "--port", "8003"]
