# server — 메인Pi

- 설계: `../docs/specs/2026-09-14-s2-server-design.md`
- **메인Pi 배포 = Docker** (2026-09-23 팀 결정): 리포 루트에서 `docker compose up -d --build` → http://<호스트>:8000. 이미지 정의는 `server/Dockerfile`(빌드 컨텍스트는 리포 루트 — `../lora_proto` path 의존), 설정은 루트 `compose.yaml`, DB 는 볼륨 `/data/main.db`. 노트북에서도 같은 명령으로 메인Pi 와 똑같은 서버를 띄울 수 있다(Docker Desktop).
- 개발용 직접 기동: `uv sync && uv run alembic upgrade head && uv run uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000`
  (반드시 `--workers 1`, 즉 기본값 그대로 단일 워커로 — WS 연결 레지스트리와 `lora_service/api.py`의 상태가 프로세스 메모리에 있어 워커가 여러 개면 모뎀Pi 연결·outbox 디스패치가 워커마다 따로 놀아 깨진다)
- 확인: http://localhost:8000/static/index.html · http://localhost:8000/docs
- 모뎀Pi 등록: `POST /api/lora/modems {"modem_id": "mjc-eng"}` → 응답의 `token`을 모뎀Pi 설정에 넣는다(평문은 이때 한 번만 보인다).
- 시간표 CSV: `POST /api/import/slots` 본문에 CSV 텍스트(`text/csv`, UTF-8). 규격·출처 규칙은 `../docs/specs/2026-09-16-s2b-csv-import-design.md` §2. `?dry_run=true`로 미리보기.
- env: `SERVER_DB`(기본 `main.db`), `STATUS_HOUR_UTC`(기본 18)
- 테스트: `uv run pytest -q`
