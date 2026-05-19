# syntax=docker/dockerfile:1.7
# React/Vite 빌드 후 nginx로 서빙.
# 브라우저는 이 컨테이너에서 번들만 받고, API 호출은 host의 authoring(:8001)·judge(:8002)로 직접 요청.

FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
