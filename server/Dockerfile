# syntax=docker/dockerfile:1
# 메인Pi 서버 이미지 — FastAPI + lora_service(WS 허브·outbox).
#
# 빌드 컨텍스트는 **리포 루트**다: 서버가 `../lora_proto` 를 path 의존으로 쓰기 때문이다.
#   docker compose up -d --build            (루트의 compose.yaml)
#   docker build -f server/Dockerfile .     (직접 빌드)
#
# 멀티아치: python·uv 공식 이미지가 amd64(노트북)·arm64(Raspberry Pi) 둘 다 있다.

# ---------- build: uv 로 잠금 파일 그대로 설치 ----------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
# 런타임과 같은 경로(/app)에 설치한다 — venv 안의 절대 경로(파이썬·editable lora_proto)가 그대로 맞는다.
WORKDIR /app
COPY lora_proto/ lora_proto/
COPY server/pyproject.toml server/uv.lock server/
# 의존성 먼저(코드가 바뀌어도 이 레이어는 캐시된다)
RUN --mount=type=cache,target=/root/.cache/uv \
    cd server && uv sync --frozen --no-dev --no-install-project
COPY server/ server/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd server && uv sync --frozen --no-dev

# ---------- runtime ----------
FROM python:3.12-slim-bookworm
RUN useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p /data && chown app:app /data
COPY --from=build --chown=app:app /app /app
WORKDIR /app/server
ENV PATH="/app/server/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SERVER_DB=/data/main.db
USER app
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
# 마이그레이션 → 서버. 워커는 반드시 1개(uvicorn 기본값) — WS 연결 레지스트리와 outbox 디스패치 상태가
# 프로세스 메모리에 있어 워커가 여럿이면 깨진다(server/README.md). --workers 를 붙이지 말 것.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000"]
