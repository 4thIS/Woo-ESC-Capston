# server — 메인Pi

- 설계: `../docs/specs/2026-09-14-s2-server-design.md` · 인증: `../docs/specs/2026-09-23-s4a-auth-design.md`
- `.env` 준비: `cp .env.example .env` 후 값 채우기 — `JWT_SECRET`(32자 이상, 예 `python -c "import secrets;print(secrets.token_urlsafe(48))"`), `STUDENT_WEB_URL`(학생 웹 오리진), `MAIL_BACKEND=smtp`면 Gmail **앱 비밀번호**(2단계 인증 켠 계정에서 발급)를 `SMTP_USER`/`SMTP_PASSWORD`에. 개발은 `DEBUG=1 MAIL_BACKEND=console`(메일을 콘솔에 출력, SMTP 불필요).
- 기동: `uv sync && uv run alembic upgrade head && uv run --env-file .env uvicorn --factory app.main:create_app --host 0.0.0.0 --port 8000 --workers 1 --no-server-header`
  (반드시 `--workers 1` — WS 연결 레지스트리와 `lora_service/api.py`의 상태가 프로세스 메모리에 있어 워커가 여러 개면 모뎀Pi 연결·outbox 디스패치가 워커마다 따로 놀아 깨진다. `--no-server-header`로 응답에 서버 버전 노출 안 함)
- 초기 설정(CLI, `uv run --env-file .env python -m app.cli <cmd>`):
  - `create-school --name 우송대 --net-id 75 --email-domain wsu.ac.kr` — 도메인은 학생 웹메일 가입 판별에 쓰인다.
  - `create-admin --school-id 1 --email admin@wsu.ac.kr --name 관리자` — 비밀번호는 프롬프트(getpass)로 입력, argv엔 안 받는다.
  - 도메인·이름 변경은 `update-school --id 1 --email-domain ...`. 그 외 `set-user`(관리자 계정 활성/정지·비밀번호 재설정), `assign-modem`(school_id 미배정 모뎀 배정)도 있다.
- 확인: http://localhost:8000/static/index.html · http://localhost:8000/docs — 이 둘은 **`DEBUG=1`일 때만** 마운트된다(운영에서는 꺼짐). 4주차 Pi↔Pi 통합 확인도 `DEBUG=1`로 띄운 이 페이지로 한다.
- 인증: `/api/health`·`/api/auth/*`를 뺀 모든 `/api/*`는 `Authorization: Bearer <token>` 필요. 토큰은 `POST /api/auth/login {email, password}` → `{token, role, school_id, name}`. 관리자는 자기 학교 리소스만 보고 고칠 수 있다(타 학교는 404).
- 학생 가입: 학교 웹메일로 2단계(이메일 제출 → 메일 링크에서 이름·학번·비밀번호 입력) → 관리자 승인 대기. 자세한 흐름·상태 전이는 `../docs/specs/2026-09-23-s4a-auth-design.md` §2 참고.
- 모뎀Pi 등록: `POST /api/lora/modems {"modem_id": "mjc-eng"}` → 응답의 `token`을 모뎀Pi 설정에 넣는다(평문은 이때 한 번만 보인다).
- 시간표 CSV: `POST /api/import/slots` 본문에 CSV 텍스트(`text/csv`, UTF-8). 규격·출처 규칙은 `../docs/specs/2026-09-16-s2b-csv-import-design.md` §2. `?dry_run=true`로 미리보기.
- 시각 필드(`*_at`)는 모두 UTC이며 `Z` 접미사 없이 저장·응답된다.
- 관리자 API(경고·요약·건물 단위 조회): 설계는 `../docs/specs/2026-09-23-s4b-admin-api-design.md`.
  - `GET /api/admin/summary?preview=` — 경고 8종 카운트+미리보기(기본 5, 최대 20), 총계.
  - `GET /api/admin/nodes?only=&building_id=` — 기대 노드(학교 rooms × units) × 상태, `only`로 경고 필터.
  - `GET /api/admin/outbox/failed?days=&limit=` — 최근 실패 outbox(기본 7일, 관리자 취소 제외).
  - `GET /api/buildings/{id}/{slots|reservations|exams|outbox}` — 건물 단위 시간표·예약·시험기간·outbox 목록.
  - 예약·시험기간 등록 POST는 `id` 생략 시 서버가 채번하고 응답 `Enqueued.id`로 알려준다(지정 시 같은 방의 기존 id만 수정).
- 테스트: `uv run pytest -q`

## env

| 키 | 기본값 | 설명 |
|---|---|---|
| `SERVER_DB` | `main.db` | SQLite 파일 경로 |
| `STATUS_HOUR_UTC` | `18` | 상태 요약 기준 시각(UTC, KST 03:00) |
| `JWT_SECRET` | (필수) | HS256 서명 키, 32자 이상 아니면 기동 실패 |
| `JWT_TTL_H` | `24` | 발급 토큰 유효시간(시간) |
| `STUDENT_WEB_URL` | (필수) | 학생 웹 오리진 — 가입/재설정 메일 링크에 사용 |
| `MAIL_BACKEND` | `smtp` | `smtp`(Gmail SMTP_SSL) 또는 `console`(개발용, 콘솔 출력 — 토큰이 로그에 남으므로 `DEBUG=1` 일 때만 허용, 아니면 기동 실패) |
| `SMTP_USER` | (빈 값) | `MAIL_BACKEND=smtp`면 필수 — Gmail 주소 |
| `SMTP_PASSWORD` | (빈 값) | `MAIL_BACKEND=smtp`면 필수 — Gmail **앱 비밀번호** |
| `MAIL_FROM` | `SMTP_USER` | 발신자 표시 주소 |
| `DEBUG` | `0` | `1`이면 `/docs`·`/redoc`·`/openapi.json`·`/static` 마운트 |
| `CORS_ORIGINS` | (빈 값) | 콤마 구분 허용 오리진. 빈 값 = 전부 차단 |
