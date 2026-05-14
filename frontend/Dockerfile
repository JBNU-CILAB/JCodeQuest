# syntax=docker/dockerfile:1.7
# Build context: 모노레포 루트.
# Vite는 import.meta.env를 빌드 타임에 인라인하므로 VITE_* 변수는 build args로 받는다.

FROM node:20-alpine AS build
WORKDIR /app/frontend

# 의존성 설치 캐시 분리.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# 빌드 타임에 인라인될 환경변수.
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_API_BASE_URL
ENV VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY \
    VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 5173
