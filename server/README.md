# server — 메인Pi

- 설계: `../docs/specs/2026-09-14-s2-server-design.md` · 인증: `../docs/specs/2026-09-23-s4a-auth-design.md`
- **메인Pi 배포 = Docker** (2026-09-23 팀 결정) — 리포 루트에서:
  ```bash
  cp server/.env.example server/.env        # 값 채우기 (아래 표) — 커밋 금지, 이미지에도 안 들어간다(.dockerignore)
  docker compose up -d --build              # 빌드 + 기동. DB 는 볼륨 /data/main.db (SERVER_DB 는 compose 가 고정)
  docker compose exec server python -m app.cli create-school --name 우송대 --net-id 75 --email-domain wsu.ac.kr
  docker compose exec server python -m app.cli create-admin --school-id 1 --email admin@wsu.ac.kr --name 관리자
  docker compose logs -f server
  ```
  이미지 정의는 `server/Dockerfile`(빌드 컨텍스트는 리포 루트 — `../lora_proto` path 의존), 설정은 루트 `compose.yaml`(`env_file: server/.env`). 노트북에서도 같은 명령으로 메인Pi 와 똑같은 서버를 띄울 수 있다(Docker Desktop). 아래 `uv run …` 기동·CLI 는 **개발용**이다.
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
- 학생·관리자 예약·일일 작업·분석 API: 설계는 `../docs/specs/2026-09-23-s10-student-analytics-design.md`.
  - 학생(로그인 필요, 자기 학교의 reservable 방만):
    - `GET /api/student/rooms/free?at=&building_id=` — 지금(또는 `at`) 비어 있는 방 목록.
    - `GET /api/student/rooms?building_id=` — 전체 방 현재 상태.
    - `GET /api/student/rooms/{id}/week?date=` — 그 방 주간 시간표·예약·시험기간.
    - `POST /api/student/rooms/{id}/reservations` — 예약 신청(하루 10회 초과 시 429).
    - `GET /api/student/me/reservations?status=` — 내 예약 목록(기본 `requested,approved`).
    - `POST /api/student/me/reservations/{id}/cancel` — 신청 철회 또는 시작 전 취소.
    - `POST /api/student/me/reservations/{id}/checkin` — 체크인.
  - 관리자(자기 학교 스코프):
    - `GET /api/admin/reservations?status=&building_id=&date_from=&date_to=&limit=` — 예약 목록(기본 `requested`, `limit` 기본 500·최대 1000). 시작이 지난 신청은 승인할 수 없어 빠진다.
    - `POST /api/admin/reservations/{id}/{approve|reject|cancel}` — 승인·거절·취소.
    - `GET /api/admin/analytics/allocation?from=&to=&building_id=&group=` — 배정률(방/건물/요일별).
    - `GET /api/admin/analytics/free-slots?date=&building_id=` — 공강 슬롯.
    - `GET /api/admin/analytics/reservations?from=&to=&group=` — 예약·No-show 통계. `requested` 는 받은 신청 전체(현재 상태 무관), 나머지는 현재 상태별 수.
    - `GET /api/admin/analytics/latency?from=&to=&type=` — 갱신 지연 히스토그램(`SLOT_SET`/`RESV_SET`/`all`).
    - `GET /api/admin/analytics/latency/samples?from=&to=&type=&limit=` — 지연 원본 샘플.
  - 일일 작업(만료·승격·실패 재동기·정리)은 KST **04:00**에 자동 실행(`daily_loop`), 필요 시 수동 `POST /api/admin/jobs/daily`. 실행 기록은 `GET /api/admin/jobs?name=daily&limit=`. 실패 재동기의 FILE 자체가 실패하면 다음 날 다시 나간다(매일 재시도 — 계속 실패하는 노드는 매일 깨움, 연속 실패 상한은 후속 검토). `errors` 에는 예외 클래스명만 남는다(자세한 내용은 서버 로그).
  - `.env` 변경 없음.
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
