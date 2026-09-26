# syntax=docker/dockerfile:1
# 학생·관리자 웹 이미지 — Vite 로 빌드한 정적 파일을 nginx 가 내보내고 /api 는 server 컨테이너로 넘긴다.
#
# 빌드 컨텍스트는 web/ 다(루트 compose.yaml 의 web 서비스).
#   docker compose up -d --build web        (웹만 다시 — 서버·모뎀Pi 연결은 그대로)
#   docker build -t woo-esc/web:local web   (직접 빌드)
#
# 멀티아치: node·nginx 공식 이미지가 amd64(노트북)·arm64(Raspberry Pi) 둘 다 있다.

# ---------- build: package.json 의 pnpm 버전 그대로, 잠금 파일 그대로 ----------
FROM node:22-bookworm-slim AS build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /web
# 의존성 먼저(코드가 바뀌어도 이 레이어는 캐시된다)
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# ---------- runtime: 정적 파일 + /api 프록시 ----------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1/healthz"]
