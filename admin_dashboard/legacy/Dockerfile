# syntax=docker/dockerfile:1.7
# 정적 HTML 1장 — nginx로 서빙. 빌드 단계도 의존성도 없다.
# 브라우저는 이 컨테이너에서 페이지만 받아오고, 실제 API 호출은 host로 매핑된
# authoring(:8001, 문제/공지/runs)과 judge(:8002, /api/submissions*) 두 서비스로
# 직접 친다. 따라서 컨테이너 내부 네트워크 의존성은 없다.

FROM nginx:1.27-alpine AS runtime

COPY admin_dashboard/index.html /usr/share/nginx/html/index.html

# nginx 기본 80 포트로 listen — compose에서 host의 6010 → container의 80으로 매핑.
EXPOSE 80
