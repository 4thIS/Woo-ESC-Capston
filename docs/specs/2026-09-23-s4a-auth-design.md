# S4a — 회원·인증 (학생 웹메일 가입·관리자 승인·JWT·학교 스코프) — 설계 (spec)

- 생성일시: 2026-09-23
- 수정일시: 2026-09-23
- 상위 문서: `2026-09-09-roadmap-design.md` §3(메인Pi 책임 "회원"), §5 S4(관리자 웹)·S10(학생 웹). 도메인·REST는 `2026-09-14-s2-server-design.md`(S2, 인증은 비목표로 뺐음), CSV는 `2026-09-16-s2b-csv-import-design.md`.
- 담당: wj @leemonta9482. 영역 `server/`. `server/lora_service/api.py`는 변경 없음(스코프는 라우터 층). `lora_service/router.py`에 가드·스코프가 붙으므로 cw 리뷰.

## 0. 배경 · 위치

S2는 "인증은 기획 미확정"이라 모든 REST를 무인증으로 열어 두었다. 관리자 웹(S4)과 학생 웹(S10)을 만들려면 **누가 무엇을 볼 수 있는지**가 먼저 정해져야 한다. 2026-09-23 확정된 기획:

- 학생은 **대학교 웹메일**로 가입 신청 → 메일 링크로 소유 확인 → **학교 관리자가 승인** → 웹메일+비밀번호로 로그인. 가입 항목은 이름·학번·웹메일·비밀번호(향후 확장).
- 학교는 웹메일 **도메인**으로 자동 판별. 학교 관리자는 자기 학교 것만(건물·강의실·시간표·모뎀Pi·ESP노드·회원) 관리.
- 학생은 자기 학교의 빈 강의실 조회 + 예약 **신청**(승인은 관리자). 예약 흐름 자체는 S10 spec.
- 메일은 Gmail SMTP, 설정은 `.env`.
- `/docs`·`/health` 등 운영 노출 면적을 줄인다 — 내부 정보가 밖으로 새지 않게.

이 spec은 그 인증·권한 계층이다. 관리자 대시보드 API(S4b)와 학생 API(S10)는 이 위에 얹는다.

## 1. 목표 · 비목표

### 목표
- 학생 가입 신청 → 메일 링크(5분) → 관리자 승인 → 로그인(JWT 24 h) 흐름.
- 비밀번호 재설정(같은 링크 흐름).
- 역할 2개 `student` / `admin`, 둘 다 **학교 스코프**. 기존 S2·S2b REST 전부를 관리자 전용 + 학교 스코프로.
- 운영 노출 면적 축소: `/docs`·`/openapi.json`·`/static`은 `DEBUG=1`일 때만, `/health`는 `{"ok": true}`뿐, 500 본문에 예외 문자열 없음, CORS 허용 목록, 브루트포스 제한.
- 관리자 계정은 CLI로 생성.

### 비목표 (이번엔 안 함 / 후속)
- 학생 예약 신청·승인·빈 강의실 조회 — S10 spec. 이 spec은 `rooms.reservable` 컬럼만 둔다.
- 프로필 수정, 회원 탈퇴, 로그인 이력, 리프레시 토큰, 강제 로그아웃(`users.token_version` 한 컬럼으로 나중에 가능), 비밀번호 정책 강화(지금은 8자 이상만).
- 슈퍼 관리자·웹에서 관리자 생성 — 전시 규모(학교 1개)에는 CLI로 충분.
- 메일 큐·재시도 — 발송 실패는 로그 + 학생의 "재발송".
- 모뎀Pi WS 인증(`/ws/modem`)은 기존 모뎀 토큰(계약 ⑥) 그대로. JWT와 무관.

## 2. 데이터 · 계약

### 2.1 스키마 (마이그레이션 `web_auth`, additive)

```
schools   + email_domain TEXT UNIQUE NULL     -- "wsu.ac.kr". NULL 이면 그 학교는 학생 가입 불가
rooms     + reservable   BOOLEAN NOT NULL DEFAULT 0  -- 학생이 예약 신청할 수 있는 방 (S10 이 사용)
modems    + school_id    INTEGER NULL FK schools     -- 등록한 관리자의 학교. 건물 배정 전 스코프 근거

users
  email         TEXT PRIMARY KEY     -- 소문자 정규화(strip + lower)
  school_id     INTEGER NOT NULL FK schools
  role          TEXT NOT NULL        -- 'student' | 'admin'
  status        TEXT NOT NULL        -- 'pending_email' | 'pending_approval' | 'active' | 'rejected' | 'disabled'
  name          TEXT NOT NULL
  student_no    TEXT NULL            -- 학번. admin 은 NULL
  pw_hash       TEXT NOT NULL        -- "scrypt$<salt hex>$<hash hex>"
  created_at    DATETIME NOT NULL
  approved_at   DATETIME NULL
  approved_by   TEXT NULL            -- 승인/거절한 관리자 email
  reject_reason TEXT NULL
  UNIQUE (school_id, student_no)     -- SQLite: NULL 은 유일성 검사에서 제외

email_tokens
  token_hash  TEXT PRIMARY KEY       -- sha256(평문). 평문은 메일에만 존재
  email       TEXT NOT NULL FK users(email) ON DELETE CASCADE
  purpose     TEXT NOT NULL          -- 'verify' | 'reset'
  expires_at  DATETIME NOT NULL      -- 발급 + 5 분
  used_at     DATETIME NULL          -- 1회용. 새 토큰 발급 시 같은 (email, purpose) 의 미사용 토큰도 채운다
  INDEX ix_email_tokens_email (email, purpose)
```

시각은 앱 관행대로 naive UTC(`app.db.utcnow`).

### 2.2 상태 전이

```
signup ──▶ pending_email ──verify──▶ pending_approval ──approve──▶ active ◀──enable── disabled
                                          │                          │  ▲               ▲
                                          └────reject────▶ rejected  └──disable────────┘
```

- `rejected`·`disabled` email 로 다시 `signup` → 409. 풀어 주는 건 관리자(`enable`은 `disabled`만, `rejected`는 후속 — 지금은 CLI/DB).
- `pending_email` 로 다시 `signup` → 사용자 정보는 그대로 두고 verify 토큰만 재발급·재발송(비밀번호·이름은 갱신하지 않는다 — 첫 신청이 진짜 소유자가 아닐 수 있으므로 소유 확인 전엔 아무것도 덮지 않는다).
- 관리자 계정: CLI 가 `role=admin, status=active, student_no=NULL` 로 직접 생성. 인증 메일 없음.

### 2.3 토큰

| | 값 |
|---|---|
| 메일 토큰 | `secrets.token_urlsafe(32)`. DB 는 sha256 hex. 만료 **5 분**. 1회용. 재발송 간격 **60 s** |
| 링크 | `{STUDENT_WEB_URL}/verify?token=…`, `{STUDENT_WEB_URL}/reset?token=…` — SPA 가 `token` 을 읽어 API 호출. 링크에 서버 주소 없음 |
| JWT | HS256(`PyJWT`), `exp` = 발급 + `JWT_TTL_H`(기본 24 h), 클레임 `sub`=email, `role`, `school_id`. 시크릿 `JWT_SECRET`(.env, 없으면 기동 실패) |
| 비밀번호 | `hashlib.scrypt(pw, salt=16 B, n=2**14, r=8, p=1)`. 저장 `scrypt$<salt hex>$<hash hex>`. 규칙: 8자 이상 |

JWT 검증 뒤 **매 요청 `users` 조회**해 `status == active` 를 다시 본다 — `disabled` 는 토큰 만료를 기다리지 않고 즉시 막힌다(조회 1건, SQLite ms).

## 3. 접근 제어 / 제약

### 3.1 가드 (`app/auth/deps.py`)

| 이름 | 조건 | 실패 |
|---|---|---|
| `current_user` | `Authorization: Bearer <jwt>` → 서명·만료 → `users[sub]` 존재·`active` | 401 `{"detail": "인증 필요"}` |
| `require_admin` | `current_user.role == "admin"` | 403 |
| `require_student` | `role == "student"` | 403 |

### 3.2 엔드포인트 등급

| 등급 | 경로 | 가드 |
|---|---|---|
| 공개 | `POST /api/auth/{signup,verify,resend,login,forgot,reset}` | 없음. 존재 여부·상태가 응답으로 새지 않게 202/401 통일(§4) |
| 학생 | `GET /api/auth/me`, S10 `/api/student/*` | `current_user` (+ 학교 스코프) |
| 관리자 | 기존 `/api/schools`, `/api/buildings`, `/api/rooms/**`, `/api/import/slots`, `/api/lora/**`, 신규 `/api/admin/**` | `require_admin` + 학교 스코프 |
| 기계 | `/ws/modem` | 모뎀 토큰(계약 ⑥). 불변 |
| 운영 | `GET /api/health` | 없음. 본문 **`{"ok": true}` 만**(현재도 그렇다 — 유지 규칙으로 못 박음) |
| 개발 | `/docs`, `/redoc`, `/openapi.json`, `/static/*` | **`DEBUG=1` 일 때만 마운트**. 기본 404. OpenAPI 스키마 = 내부 엔드포인트 목록이라 노출 면적 |

### 3.3 학교 스코프

관리자 토큰의 `school_id` = `S`.

| 리소스 | 판정 | 안 맞으면 |
|---|---|---|
| `schools` | `id == S` 만 조회·수정. **생성·삭제는 CLI**(`create-school`) — `POST/DELETE /api/schools` 제거 | 404 |
| `buildings` | `school_id == S` | 404 |
| `rooms`·slots·reservations·exam_periods·sync·cmd | `room → building.school_id == S` | 404 |
| `import/slots` | CSV `school` 컬럼이 `S` 의 이름과 다르면 그 행 오류 `"school: 다른 학교"` | 400 errors |
| `lora/modems` | `modems.school_id == S`. 등록 시 `school_id = S` 로 채움 | 404 / 목록 필터 |
| `lora/outbox`, `lora/status`, `lora/pending` | outbox·status는 `(bld, room) → rooms → building.school_id`; `pending_devices` 는 `modem_id → modems.school_id` | 목록 필터, 단건 404 |
| `admin/users` | `users.school_id == S` | 404 |

- 타 학교 리소스는 **403 이 아니라 404** — 존재 여부를 숨긴다.
- 구현: 라우터의 `_get(s, Model, id)` 를 `_get_scoped(s, Model, id, user)` 로 바꾸고, 목록 쿼리는 `school` 조인 한 번. `lora_service/api.py` 는 학교를 모른다(계층 규율) — 스코프는 **라우터 층에서만**.
- `Topology`·`RecordProvider`·허브는 학교와 무관 — 불변.

### 3.4 노출 면적 · 남용 방지

| 항목 | 규칙 |
|---|---|
| 500 | 전역 핸들러 `{"detail": "internal error"}`. 예외 문자열은 로그에만. CSV 임포트의 `f"... ({e}) ..."` 500 문구도 고정 문구로(방 이름은 남김) |
| 409 | 기존 `"constraint violation"` 유지 |
| 로그 | 비밀번호·메일 토큰·JWT 는 절대 기록 안 함. 로그인 실패는 email 만 INFO |
| 브루트포스 | `login`·`resend`·`forgot`·`signup` 은 **email 당 분당 5회**, 초과 429. 프로세스 메모리 dict(단일 워커 — README 의 `--workers 1` 규칙과 같은 근거). 재시작 시 초기화 감수 |
| CORS | `CORS_ORIGINS`(.env, 쉼표 구분) 만 허용. 기본 빈 값 = 차단. 자격증명 헤더 허용(Bearer) |
| 응답 스키마 | `UserOut` 화이트리스트(`email, school_id, role, status, name, student_no, created_at, approved_at`). `pw_hash`·`token_hash` 는 어떤 응답에도 없음 |
| `Server` 헤더 | uvicorn `--no-server-header`. README 기동 명령 갱신 |
| 상태 노출 | `login` 실패는 401 `"이메일 또는 비밀번호가 틀립니다"` 로 통일. 예외 하나: `pending_approval` 은 403 `"승인 대기 중"`(학생 안내 필요). `resend`·`forgot` 은 존재 여부와 무관하게 202 |

## 4. 인터페이스 계약

### 4.1 공개 `/api/auth/*`

| 메서드·경로 | 본문 | 동작 | 응답 |
|---|---|---|---|
| `POST /signup` | `email, password(≥8), name, student_no` | email 정규화 → 도메인 = `schools.email_domain` 인 학교 찾기(없으면 400 `"학교 웹메일이 아닙니다"`) → `users` 생성 `pending_email` → verify 토큰 → 메일(백그라운드) | 202 `{"status": "pending_email"}`. 같은 email: `pending_email` 이면 재발급·재발송(정보 갱신 없음), 그 외 409 |
| `POST /verify` | `token` | `consume(token, "verify")` → 사용자 `pending_approval` | 200 `{"status": "pending_approval"}`. 만료·무효·재사용 400 `"링크가 만료되었거나 잘못되었습니다"` |
| `POST /resend` | `email` | `pending_email` 이고 마지막 발급 60 s 경과면 재발급·재발송 | 항상 202 |
| `POST /login` | `email, password` | `active` + scrypt 검증 → JWT | 200 `{"token", "role", "school_id", "name"}`. 실패 401(§3.4), `pending_approval` 403 |
| `POST /forgot` | `email` | `active` 면 `reset` 토큰·메일 | 항상 202 |
| `POST /reset` | `token, password(≥8)` | `consume(token, "reset")` → `pw_hash` 교체 → 그 email 의 미사용 토큰 전부 무효 | 200. 실패 400 |
| `GET /me` | Bearer | 토큰의 사용자 | `UserOut` |

### 4.2 관리자 `/api/admin/users/*` (`require_admin`, 자기 학교)

| 메서드·경로 | 동작 | 응답 |
|---|---|---|
| `GET /api/admin/users?status=` | 목록. `status` 없으면 전체 | `list[UserOut]` |
| `POST /api/admin/users/{email}/approve` | `pending_approval → active`, `approved_at/by`, 승인 메일 | `UserOut`. 상태 불일치 409 |
| `POST /api/admin/users/{email}/reject` `{reason}` | `pending_approval → rejected`, `reject_reason`, 거절 메일(사유 포함) | `UserOut`. 409 |
| `POST /api/admin/users/{email}/disable` | `active → disabled` | `UserOut`. 409 |
| `POST /api/admin/users/{email}/enable` | `disabled → active` | `UserOut`. 409 |

관리자 자신(`role=admin`)은 이 목록에 나오되 `disable` 대상이 아니다(자기 학교 관리자 계정을 웹에서 끄는 건 CLI 몫) — 400.

### 4.3 기존 엔드포인트 변경 (additive 아님 — BREAKING, S2 REST 소비자는 아직 정적 페이지뿐)

- 모든 `/api/schools|buildings|rooms|import|lora/*` 에 `require_admin` + 학교 스코프.
- `POST /api/schools`, `DELETE /api/schools/{id}` 제거 → CLI `create-school --name --net-id --email-domain`.
- `PATCH /api/schools/{id}` 는 `email_domain` 도 받는다(additive).
- `RoomIn/RoomOut` 에 `reservable: bool = False`(additive).
- `ModemOut` 에 `school_id`(additive).
- `static/index.html`: 로그인 폼(email·비밀번호) → 토큰을 메모리에 두고 모든 `fetch` 에 Bearer. `DEBUG=1` 에서만 뜨는 개발 페이지.

### 4.4 CLI (`app/cli.py`, `uv run python -m app.cli …`)

```
create-school --name 우송대 --net-id 75 --email-domain wsu.ac.kr
create-admin  --school-id 1 --email admin@wsu.ac.kr --name 관리자 --password …   # 같은 email 있으면 오류
```

## 5. 영역별 영향

- `server/app/auth/` (신규): `models.py`(User, EmailToken) · `password.py`(hash/verify) · `tokens.py`(메일 토큰 issue/consume, JWT encode/decode) · `mailer.py`(send + 템플릿 3개) · `deps.py`(가드·스코프 헬퍼) · `router.py`(§4.1·4.2) · `ratelimit.py`.
- `server/app/cli.py` (신규), `server/alembic/versions/web_auth_<rev>.py`.
- `server/app/settings.py`: §6 키. `server/app/main.py`: `DEBUG` 조건 마운트, CORS, 전역 500 핸들러, 라우터 등록.
- `server/app/domain/router.py`, `server/app/lora_service/router.py`: 가드·`_get_scoped`·목록 필터. **`lora_service/api.py`·`hub.py` 불변.**
- `server/app/schemas.py`: `UserOut`, auth 요청 모델, `RoomIn.reservable`, `ModemOut.school_id`.
- `server/tests/conftest.py`: 관리자 시드 + Bearer 자동 첨부 `client`. 기존 S2·S2b 테스트는 호출부 불변.
- `server/README.md`, `.env.example`(신규, 값 비움).
- modempi·firmware·`lora_proto`: 영향 없음. web: S4·S10 화면이 `/api/auth/*` 를 쓴다(후속).
- 로드맵 §4 계약 ⑤ "REST = OpenAPI" 에 인증 등급이 추가됨 — PR 본문에 cw 반영 요청.

## 6. 설정 (`.env`)

| 키 | 필수 | 기본 | 용도 |
|---|---|---|---|
| `JWT_SECRET` | ✅ | — | 없으면 기동 실패 |
| `STUDENT_WEB_URL` | ✅ | — | 메일 링크 prefix (예 `https://rooms.wsu.ac.kr`) |
| `SMTP_USER`, `SMTP_PASSWORD` | `MAIL_BACKEND=smtp` 면 ✅ | — | Gmail 계정 + **앱 비밀번호**(2단계 인증 필요) |
| `MAIL_FROM` | | `SMTP_USER` | 발신 표시 |
| `MAIL_BACKEND` | | `smtp` | `smtp` \| `console`(stdout, 개발·테스트) |
| `DEBUG` | | `0` | `1` 이면 `/docs`·`/openapi.json`·`/static` |
| `CORS_ORIGINS` | | 빈 값 | 쉼표 구분 허용 origin |
| `JWT_TTL_H` | | `24` | |

메일: `smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)` + `email.message.EmailMessage`. 인터페이스 `send(to, subject, body)` 하나. 템플릿은 f-string 함수 3개(인증·재설정·승인/거절). 호출은 전부 `BackgroundTasks`, 실패는 `log.exception` 만.

## 7. 무회귀 · 롤아웃

- 마이그레이션 additive(테이블 2 + 컬럼 3). 기존 행 영향 없음(`reservable` 0, `modems.school_id` NULL → 관리자가 다음 등록/배정 때 채워짐. 기존 모뎀은 CLI 없이 `PATCH /api/lora/modems/{id}`… 은 없으므로 **마이그레이션에서 `buildings.modem_id` 로 역추적해 채운다**).
- 기존 테스트 전부 통과(conftest 관리자 Bearer). 테스트 수 유지 + 아래 추가.
- 테스트(전부 `TestClient`, `mailer.send` monkeypatch 로 캡처, `clock` 주입):
  - 가입: 도메인 불일치 400 / 정상 202 + 메일 캡처 / 중복 email 상태별(pending_email 재발송·정보 불변, active 409, rejected 409) / 비번 7자 422
  - 링크: verify 성공 → `pending_approval` / 재사용 400 / 5 분 경과 400 / 새 발급 시 이전 토큰 무효 / resend 60 s 이내 무시
  - 로그인: 상태별(pending_email 401, pending_approval 403, active 200, disabled 401) / 비번 틀림 401 / JWT 클레임 / 만료 토큰 401 / disabled 즉시 401
  - 재설정: forgot 202(없는 email 도 202) / reset 후 옛 비번 401·새 비번 200 / 토큰 1회용
  - 관리자: approve·reject·disable·enable 전이와 409 / 타 학교 사용자 404 / 학생 토큰으로 관리자 API 403 / 관리자 자신 disable 400
  - 스코프: 관리자 A 가 학교 B 의 건물·강의실·슬롯·모뎀·outbox·status·pending → 404 또는 목록 제외 / CSV `school` 불일치 행 오류 / 모뎀 등록 시 `school_id` 채워짐
  - 노출 면적: `DEBUG=0` 에서 `/docs`·`/openapi.json`·`/static/index.html` 404, `DEBUG=1` 200 / `/api/health` 본문 == `{"ok": true}` / 500 본문에 예외 문자열 없음 / 응답 JSON 어디에도 `pw_hash`·`token_hash` 없음 / 6번째 로그인 시도 429 / CORS 미허용 origin 에 `Access-Control-Allow-Origin` 없음
  - CLI: `create-school`·`create-admin` → 로그인 가능, 중복 오류

## 8. 성공 기준

- `.env` 에 Gmail 앱 비밀번호를 넣고 실제 웹메일로 가입 → 5 분 안에 링크 클릭 → 관리자 승인 → 로그인 → `GET /api/auth/me` 가 학생 정보를 돌려준다.
- 관리자 A 토큰으로 학교 B 의 강의실 id 를 찍으면 404, 목록에도 없다.
- `DEBUG` 없이 기동한 서버에서 `/docs` 404, `/api/health` 는 `{"ok": true}` 8바이트.
- 기존 S2·S2b 테스트 전부 통과.

## 9. 열린 결정 (plan 단계에서 확정)

- `rejected` 를 다시 신청 가능하게 푸는 API — 지금은 CLI/DB. 관리자 웹에서 필요해지면 `enable` 을 `rejected` 에도 허용.
- 브루트포스 카운터의 키를 email 만 할지 email+IP 로 할지 — 단일 워커·리버스 프록시 뒤라 IP 신뢰가 애매해 email 만.
- `modems.school_id` 마이그레이션 역추적: 건물 미배정 모뎀은 NULL 로 남는다 → 어느 관리자 목록에도 안 보임. 전시 규모에서 해당 없음, 필요하면 CLI `assign-modem`.
- 승인·거절 메일 문구 — 최소(한 줄 + 사유). 화면 스펙(mh) 오면 다듬음.
