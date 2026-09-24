# S4a — 회원·인증 (학생 웹메일 가입·관리자 승인·JWT·학교 스코프) — 설계 (spec)

- 생성일시: 2026-09-23
- 수정일시: 2026-09-23 (r2 — PR #38 cw 리뷰 반영: 가입 2단계화(비밀번호는 링크 확인 뒤), 이메일 형식 검증, 커밋 뒤 메일, 스코프 구멍 4개, token_version, bld 전역 유일, PATCH 부분 수정, 노출 면적 보강) (r3 — 재검토: 학번 부분 유일·거절 뒤 재신청, 링크 5분+입력 30분, 메일 종류별 상한·도메인 상한, 레이트리밋 키별 창, verify 학번 조회 제한, `/lora/time` 10분) (r5 — PR #42 구현 리뷰: 로그인은 세션을 닫은 뒤 scrypt·대기 2 s 초과 503, 로그인 한도 IP 당, scrypt 는 쓰기 락 밖, 원자적 1회용 토큰, 도메인 상한은 존재 조회 전, 메일 일일 상한, 학번 대문자, 예약·시험 id 다른 방 409)
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
- 프로필 수정, 회원 탈퇴, 로그인 이력, 리프레시 토큰, 비밀번호 정책 강화(지금은 8자 이상만). (강제 로그아웃은 r2 에서 `users.token_version` 으로 포함.)
- 슈퍼 관리자·웹에서 관리자 생성 — 전시 규모(학교 1개)에는 CLI로 충분.
- 메일 큐·재시도 — 발송 실패는 로그 + 학생이 가입 신청을 다시 하면 재발송.
- 모뎀Pi WS 인증(`/ws/modem`)은 기존 모뎀 토큰(계약 ⑥) 그대로. JWT와 무관.

## 2. 데이터 · 계약

### 2.1 스키마 (마이그레이션 `web_auth`, additive)

```
schools   + email_domain TEXT UNIQUE NULL     -- "wsu.ac.kr". NULL 이면 그 학교는 학생 가입 불가
rooms     + reservable   BOOLEAN NOT NULL DEFAULT 0  -- 학생이 예약 신청할 수 있는 방 (S10 이 사용)
modems    + school_id    INTEGER NULL FK schools     -- 등록한 관리자의 학교. 건물 배정 전 스코프 근거
                                                     -- (컬럼은 lora_service/models.py 에 있지만 lora_service 코드는 읽지 않는다 — 라우터 스코프 전용. cw 리뷰)

users
  email         TEXT PRIMARY KEY     -- 소문자 정규화(strip + lower)
  school_id     INTEGER NOT NULL FK schools
  role          TEXT NOT NULL        -- 'student' | 'admin'
  status        TEXT NOT NULL        -- 'pending_approval' | 'active' | 'rejected' | 'disabled'
  name          TEXT NOT NULL
  student_no    TEXT NULL            -- 학번. admin 은 NULL
  pw_hash       TEXT NOT NULL        -- "scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>"
  token_version INTEGER NOT NULL DEFAULT 0   -- JWT 클레임 tv 와 비교. 재설정·disable·enable 때 +1 → 기존 토큰 무효
  created_at    DATETIME NOT NULL
  approved_at   DATETIME NULL
  approved_by   TEXT NULL            -- 승인/거절한 관리자 email
  reject_reason TEXT NULL
  UNIQUE INDEX uq_users_school_student_no (school_id, student_no)
        WHERE status IN ('pending_approval','active','disabled')   -- 부분 유일: 거절 행은 학번을 잡지 않는다(r3).
                                                                   -- SQLite: NULL(관리자)은 유일성 검사에서 제외

email_tokens
  token_hash  TEXT PRIMARY KEY       -- sha256(평문). 평문은 메일에만 존재
  email       TEXT NOT NULL          -- FK 아님: verify 토큰은 users 행이 생기기 **전**에 발급된다
  purpose     TEXT NOT NULL          -- 'verify' | 'reset'
  created_at  DATETIME NOT NULL      -- 발급 시각. 재발송 간격(60 s)·연장 상한의 기준
  expires_at  DATETIME NOT NULL      -- 발급 + 5 분. verify 는 링크를 열면(verify/open) 입력 시간 30 분으로 연장(상한 발급 + 35 분)
  used_at     DATETIME NULL          -- 1회용. 재발급은 이전 토큰을 죽이지 않는다(남이 재신청으로 열어 둔 링크를 죽이는 방해 방지) — verify·reset 성공 때 그 email 의 미사용 토큰 전부 채움
  INDEX ix_email_tokens_email (email, purpose)
```

시각은 앱 관행대로 naive UTC(`app.db.utcnow`).

**`users` 행은 링크 확인(verify) 때 처음 생긴다.** 가입 신청 단계엔 DB 에 토큰 행만 남으므로 남의 웹메일로 먼저 신청해 계정·학번을 선점할 수 없다(r2, 리뷰 🔴2). `pending_email` 상태는 없앴다.

### 2.2 상태 전이

```
signup(email) ──메일 링크──▶ verify(token, name, student_no, password) ──▶ pending_approval ──approve──▶ active ◀──enable── disabled
                                                                              │                             │               ▲
                                                                              └──reject──▶ rejected          └──disable──────┘
```

- **가입은 2단계다(r2).** ① 웹메일만 입력 → 인증 링크 발송(DB 엔 토큰 행만). ② 링크 페이지에서 **이름·학번·비밀번호** 입력 → `users` 행 생성(`pending_approval`). 비밀번호를 정하는 사람 = 메일함을 가진 사람이므로 선점·탈취가 없다. 수집 항목(이름·학번·웹메일·비밀번호)은 그대로.
- 이미 `users` 행이 있는 email 로 `signup` → 아무것도 보내지 않고 **202**(존재 여부 숨김). `verify` 때 행이 이미 있으면 400(링크 무효와 같은 문구).
- **예외: `rejected` 는 다시 신청할 수 있다(r3).** signup 이 메일을 보내고, verify 가 거절 행을 지우고 새 `pending_approval` 행을 만든다(거절 사유는 사라짐). 학번 오타로 거절된 본인이 막히지 않게. 남용은 signup 레이트리밋·도메인 상한과 메일함 소유 요구가 막는다. `enable` 은 `disabled` 만.
- 학번은 부분 유일 인덱스라 **거절 행이 학번을 잡지 않는다** — 내부자가 남의 학번으로 신청해 거절돼도 피해자는 가입할 수 있다(r3, 리뷰 🟡).
- 관리자 계정: CLI 가 `role=admin, status=active, student_no=NULL` 로 직접 생성. 인증 메일 없음.

### 2.3 토큰

| | 값 |
|---|---|
| 메일 토큰 | `secrets.token_urlsafe(32)`. DB 는 sha256 hex. 링크를 **5 분 안에 열어야** 한다(기획). 1회용. 같은 (email, purpose) 발송 간격 **60 s** |
| verify 입력 시간 | 2단계 가입은 링크를 연 뒤 이름·학번·비밀번호를 입력한다 — 5 분에 입력까지 넣으면 빠듯하다(r3). 링크 페이지가 먼저 `POST /verify/open` 을 부르면 토큰을 **소비하지 않고** 확인하고 만료를 `min(지금 + 30 분, 발급 + 35 분)` 로 늘린다. 몇 번 열어도 상한은 발급 + 35 분. reset 은 입력이 비밀번호 하나라 연장 없음 |
| 링크 | `{STUDENT_WEB_URL}/verify#token=…`, `{STUDENT_WEB_URL}/reset#token=…` — **fragment** 라 정적 서버 접근 로그와 `Referer` 에 토큰이 남지 않는다(자체 점검 🟡). SPA 가 `location.hash` 에서 읽고 `history.replaceState` 로 지운 뒤 API 호출. 학생 웹은 `<meta name="referrer" content="no-referrer">`. 링크에 서버 주소 없음. GET 은 토큰을 건드리지 않는다(메일 스캐너가 열어도 안전) |
| JWT | HS256(`PyJWT`), `exp` = 발급 + `JWT_TTL_H`(기본 24 h), 클레임 `sub`=email, `role`, `school_id`, `tv`=`token_version`, `iat`. 디코드 시 `require=["exp", "sub", "tv"]`. 시크릿 `JWT_SECRET`(.env, 없거나 **32자 미만이면 기동 실패**) |
| 비밀번호 | `hashlib.scrypt(pw, salt=16 B, n=2**14, r=8, p=1)`. 저장 `scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>` — 파라미터를 저장해 나중에 올려도 옛 해시 검증 가능. n=2^14 는 OWASP 권고(2^17)보다 낮다 — Pi 메모리(2^17·r8 = 요청당 128 MB) 때문의 의도된 선택. 규칙: 8자 이상 |
| 이메일 | 단일 주소만: `^[a-z0-9._+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$` (소문자 정규화 뒤 — `@` 1개, 쉼표·공백·꺾쇠·따옴표 불가). 도메인은 `@` 뒤 전체. 어긋나면 422 (r2, 리뷰 🔴1) |

JWT 검증 뒤 **매 요청 `users` 조회**해 `status == active` 와 `tv == token_version` 을 다시 본다 — `disabled`·비밀번호 재설정은 토큰 만료를 기다리지 않고 즉시 막힌다(조회 1건, SQLite ms).

## 3. 접근 제어 / 제약

### 3.1 가드 (`app/auth/deps.py`)

| 이름 | 조건 | 실패 |
|---|---|---|
| `current_user` | `Authorization: Bearer <jwt>` → 서명·만료 → `users[sub]` 존재·`active`·`tv` 일치 | 401 `{"detail": "인증 필요"}` |
| `require_admin` | `current_user.role == "admin"` | 403 |
| `require_student` | `role == "student"` | 403 |

### 3.2 엔드포인트 등급

| 등급 | 경로 | 가드 |
|---|---|---|
| 공개 | `POST /api/auth/{signup,verify/open,verify,login,forgot,reset}` | 없음. 존재 여부·상태가 응답으로 새지 않게 202/401 통일(§4) |
| 학생 | `GET /api/auth/me`, S10 `/api/student/*` | `current_user` (+ 학교 스코프) |
| 관리자 | 기존 `/api/schools`, `/api/buildings`, `/api/rooms/**`, `/api/import/slots`, `/api/lora/**`, 신규 `/api/admin/**` | `require_admin` + 학교 스코프 |
| 기계 | `/ws/modem` | 모뎀 토큰(계약 ⑥). 불변 |
| 운영 | `GET /api/health` | 없음. 본문 **`{"ok": true}` 만**(현재도 그렇다 — 유지 규칙으로 못 박음) |
| 개발 | `/docs`, `/redoc`, `/openapi.json`, `/static/*` | **`DEBUG=1` 일 때만 마운트**. 기본 404. OpenAPI 스키마 = 내부 엔드포인트 목록이라 노출 면적. 4주차 Pi↔Pi 통합 확인 페이지는 `DEBUG=1` 로 띄운다(README) |

### 3.3 학교 스코프

관리자 토큰의 `school_id` = `S`.

| 리소스 | 판정 | 안 맞으면 |
|---|---|---|
| `schools` | `id == S` 만 조회·수정. **생성·삭제는 CLI**(`create-school`) — `POST/DELETE /api/schools` 제거. PATCH 로 바꿀 수 있는 건 `name` 뿐 — `net_id`·`email_domain` 은 CLI 전용(관리자가 `gmail.com` 같은 도메인을 선점하지 못하게) | 404 |
| `buildings` | `school_id == S`. 생성·수정 시 **`modem_id` 는 `modems.school_id == S` 인 것만**(타교 모뎀 config 오염 방지, 🔴4b), **`bld` 가 다른 학교 건물에 이미 있으면 409**(공중 주소 `(bld, room)` 은 전역 — S2 §9 파킹 항목을 규칙으로, 🔴4c) | 404 / 409 |
| `rooms`·slots·reservations·exam_periods·sync·cmd | `room → building.school_id == S` | 404 |
| 예약·시험 `id` 지정 upsert | 기존 행이 **같은 방**이고 (S10 뒤엔) `status == 'approved'` 일 때만 수정. 다른 방·다른 학교·신청 상태 행이면 409, 없는 id 는 그 id 로 생성. 방 이동은 삭제 후 재생성 (🔴4a — S4b §2.5 가 구현) | 409 |
| `import/slots` | CSV 의 학교·건물·방 조회를 **`School.id == S` 로 한정**(이름은 유일하지 않고 PATCH 로 바뀜). 다른 학교 이름이면 그 행 `"school: 다른 학교"` (🔴4d) | 400 errors |
| `lora/modems` | `modems.school_id == S`. 등록 시 `school_id = S` 로 채움 | 404 / 목록 필터 |
| `lora/outbox`, `lora/status`, `lora/pending` | outbox·status는 `(bld, room) → rooms → building.school_id`; `pending_devices` 는 `modem_id → modems.school_id` | 목록 필터, 단건 404 |
| `lora/pending/{mac}/provision` | pending 장치의 모뎀 **과** 목표 방 **둘 다** 자기 학교 | 404 |
| `lora/time` | TIME 방송은 `api` 가 **모든 모뎀**에 보낸다(학교 개념 없음). 반복 호출로 전 노드를 깨우지 않게 **전역 10 분에 1회**(TIME 은 원래 매시 1회라 수동 방송은 드물다), 초과 429 | 429 |
| `admin/users` | `users.school_id == S` | 404 |

- 타 학교 리소스는 **403 이 아니라 404** — 존재 여부를 숨긴다.
- 구현: 라우터의 `_get(s, Model, id)` 를 `_get_scoped(s, Model, id, user)` 로 바꾸고, 목록 쿼리는 `school` 조인 한 번. `lora_service/api.py` 는 학교를 모른다(계층 규율) — 스코프는 **라우터 층에서만**.
- `Topology`·허브는 학교와 무관 — 불변. (`bld` 전역 유일 규칙이 이 전제를 지킨다.) `RecordProvider` 는 S10 이 예약 `status` 필터를 더한다(S10 §2.3).
- PATCH(`schools`·`buildings`·`rooms`)는 **보낸 필드만** 바꾼다(`model_dump(exclude_unset=True)`) — 빠진 필드가 기본값으로 초기화되지 않게.

### 3.4 노출 면적 · 남용 방지

| 항목 | 규칙 |
|---|---|
| 500 | 전역 핸들러 `{"detail": "internal error"}`. 예외 문자열은 로그에만. CSV 임포트의 `f"... ({e}) ..."` 500 문구도 고정 문구로(방 이름은 남김) |
| 409 | 기존 `"constraint violation"` 유지. 엔진 `hide_parameters=True` — IntegrityError 로그에 `pw_hash` 같은 파라미터가 찍히지 않게 |
| 로그 | 비밀번호·메일 토큰·JWT 는 절대 기록 안 함. 로그인 실패는 email 만 INFO |
| 브루트포스 | `login`·`forgot`·`signup`·`verify` 는 **email 당 분당 5회**, 초과 429. verify 는 409(학번 중복)가 롤백돼 같은 토큰으로 다시 낼 수 있으므로(오타 수정용) 이 제한이 학번 존재 조회를 막는다. 프로세스 메모리 dict(단일 워커 — README 의 `--workers 1` 규칙과 같은 근거). **키마다 자기 창으로** 정리(하루 창 키를 1분 뒤 지우면 한도가 풀린다 — r3). 재시작 시 초기화 감수 |
| 메일 주소당 | 같은 주소·같은 종류로는 **시간당 3통**(`mail-to:{kind}:{email}`, 초과는 202 + 발송 생략 — 종류별이라 가입 메일 남용이 그 주소의 재설정 메일을 굶기지 못한다) — 주소 하나를 61 초마다 재신청해 도메인·종류별 상한을 고갈시키는 것을 막는다. 가짜 주소를 여럿 쓰면 도메인 상한(60/h)까지는 소진될 수 있다 — 그때는 **429 로 보이고** 한 시간 뒤 풀린다(메일 한도 보호가 우선인 의도된 한계). 도메인 상한은 **가입 여부를 조회하기 전에** 확인해 모든 주소에 같은 429 — 상한을 채운 뒤 202/429 차이로 가입 여부가 새지 않게(r5) |
| 동시 부하 | scrypt 동시 2개(`BoundedSemaphore`, 요청당 16 MB), **2 s 안에 차례가 안 오면 503**. scrypt 는 **DB 연결·쓰기 락을 쥐지 않은 채** 돈다 — login 은 사용자를 읽고 세션을 닫은 뒤, verify·reset 은 토큰을 읽기만 확인 → 해시 → 짧은 쓰기 트랜잭션(원자적 소비·기록). 연결을 쥔 채 줄을 서면 풀이 바닥나 허브까지 30 s 멈춘다(r5, cw 실측). 로그인 한도는 email 당 5/분 + **IP 당 30/분**(전역 한도는 누구나 전원을 잠글 수 있어 뺐다). `ratelimit` 은 스레드 락 |
| 입력 정규화 | 학번 `^[0-9A-Za-z-]+$`(공백·전각 불가), 이름·학번 strip, 학번 **대문자로** — 같은 학번을 모양만 바꿔 두 번 만들지 못하게 |
| 1회용 토큰 | 소비는 `UPDATE … WHERE used_at IS NULL AND expires_at >= now` 의 rowcount == 1 — 같은 토큰 동시 2건이 둘 다 성공하지 않게(r5) |
| 응답 전 쓰기 | `get_db` 커밋은 응답 뒤다 — 쓰기 핸들러는 return 전 `s.flush()`(실패가 성공으로 보이지 않게) |
| 메일 상한 | **종류별 시간당**: verify 60 · reset 30 · decision(승인·거절) 200, **종류별 하루**: verify 250 · reset 100 · decision 100(Gmail 일일 500 보호 — 시간 상한만으로는 하루 수천 통이 가능했다, r5). 초과분은 발송 생략 + `log.warning`. 공용 한 통이면 가짜 가입(`junkN@학교`)이 재설정·승인 메일까지 굶긴다(r3). 가입은 추가로 **학교 도메인당 시간당 60건**(실제 발송만 셈) — 초과는 **429 로 보인다**(조용히 버리지 않음) |
| 메일·커밋 순서 | FastAPI `BackgroundTasks` 는 `get_db` 커밋 **전에** 돈다(실측). 메일은 핸들러에서 **`s.commit()` 한 뒤** `bg.add_task` — 쓰기 락을 쥔 채 SMTP(최대 10 s)를 돌리지 않고, 커밋 안 된 상태를 알리지 않는다 (🔴3) |
| 시간 누설 | 없는 email 로 로그인해도 더미 해시로 scrypt 를 한 번 돌린다(응답 시간으로 가입 여부가 새지 않게) |
| 시각 표기 | 모든 `*_at` 은 naive UTC 로 직렬화된다(`Z` 없음). 클라이언트는 UTC 로 해석한다 — 웹 `api/client.ts` 에서 한 번 변환 |
| CORS | `CORS_ORIGINS`(.env, 쉼표 구분) 만 허용. 기본 빈 값 = 차단. 자격증명 헤더 허용(Bearer) |
| 응답 스키마 | `UserOut` 화이트리스트(`email, school_id, role, status, name, student_no, created_at, approved_at`). `pw_hash`·`token_hash` 는 어떤 응답에도 없음 |
| `Server` 헤더 | uvicorn `--no-server-header`. README 기동 명령 갱신 |
| 상태 노출 | `login` 실패는 401 `"이메일 또는 비밀번호가 틀립니다"` 로 통일. 예외 하나: `pending_approval` 은 403 `"승인 대기 중"`(학생 안내 필요 — 비밀번호가 맞을 때만 보이므로 제3자에겐 새지 않음). `signup`·`forgot` 은 존재 여부와 무관하게 202 |

## 4. 인터페이스 계약

### 4.1 공개 `/api/auth/*`

| 메서드·경로 | 본문 | 동작 | 응답 |
|---|---|---|---|
| `POST /signup` | `email` | 형식 검증(422) → 정규화 → 도메인 = `schools.email_domain` 인 학교(없으면 400 `"학교 웹메일이 아닙니다"`) → `users` 에 없거나 `rejected` 이고 마지막 verify 발급 60 s 경과면 → 학교 도메인 상한(429) → verify 토큰 발급 → **commit 뒤** 메일. 재발송도 이 엔드포인트 | 202 `{"status": "sent"}` (이미 가입된 email·60 s 이내도 202, 보내지 않음). 도메인 상한 초과 429 |
| `POST /verify/open` | `token` | 소비하지 않고 확인 + 입력 시간 30 분 연장(§2.3). 링크 페이지가 처음 부른다 — 폼을 채우기 전에 만료를 알려 준다 | 200 `{"email"}`. 400(링크 무효 문구) |
| `POST /verify` | `token, name(1..50), student_no(1..20), password(≥8)` | `consume(token, "verify")` → email 의 `users` 행이 없거나 `rejected` 면 생성(거절 행은 교체, `pending_approval`, 학교는 도메인으로) → **flush**(제약 위반을 응답 전에). 같은 학교 학번이 대기·활성·정지 행에 있으면 409 `"이미 등록된 학번입니다"` — 롤백돼 토큰이 살아 있어 학번을 고쳐 다시 제출 가능 | 200 `{"status": "pending_approval"}`. 만료·무효·재사용·이미 가입 400 `"링크가 만료되었거나 잘못되었습니다"`. 분당 5회 초과 429 |
| `POST /login` | `email, password` | `active` + scrypt 검증 → JWT(`tv` 포함). 없는 email 도 더미 verify | 200 `{"token", "role", "school_id", "name"}`. 실패 401(§3.4), `pending_approval` 403 |
| `POST /forgot` | `email` | `active` 이고 60 s 경과면 `reset` 토큰 → commit 뒤 메일 | 항상 202 |
| `POST /reset` | `token, password(≥8)` | `consume(token, "reset")` → `pw_hash` 교체 → `token_version += 1`(기존 JWT 무효) → 그 email 의 미사용 토큰 전부 무효 | 200. 실패 400 |
| `GET /me` | Bearer | 토큰의 사용자 | `UserOut` |

### 4.2 관리자 `/api/admin/users/*` (`require_admin`, 자기 학교)

| 메서드·경로 | 동작 | 응답 |
|---|---|---|
| `GET /api/admin/users?status=` | 목록. `status` 없으면 전체 | `list[UserOut]` |
| `POST /api/admin/users/{email}/approve` | `pending_approval → active`, `approved_at/by`, commit 뒤 승인 메일 | `UserOut`. 상태 불일치 409 |
| `POST /api/admin/users/{email}/reject` `{reason}` | `pending_approval → rejected`, `reject_reason`, commit 뒤 거절 메일(사유 포함) | `UserOut`. 409 |
| `POST /api/admin/users/{email}/disable` | `active → disabled`, `token_version += 1` | `UserOut`. 409 |
| `POST /api/admin/users/{email}/enable` | `disabled → active`, `token_version += 1` | `UserOut`. 409 |

관리자 자신(`role=admin`)은 이 목록에 나오되 `disable` 대상이 아니다(자기 학교 관리자 계정을 웹에서 끄는 건 CLI 몫) — 400.

### 4.3 기존 엔드포인트 변경 (additive 아님 — BREAKING, S2 REST 소비자는 아직 정적 페이지뿐)

- 모든 `/api/schools|buildings|rooms|import|lora/*` 에 `require_admin` + 학교 스코프.
- `POST /api/schools`, `DELETE /api/schools/{id}` 제거 → CLI `create-school --name --net-id --email-domain`.
- `PATCH /api/schools/{id}` 는 `name` 만(부분 수정). `net_id`·`email_domain` 은 CLI(`update-school`).
- `POST/PATCH /api/buildings` — `modem_id` 학교 검사, `bld` 전역 유일(409). PATCH 는 부분 수정.
- `RoomIn/RoomOut` 에 `reservable: bool = False`(additive).
- `ModemOut` 에 `school_id`(additive).
- `static/index.html`: 로그인 폼(email·비밀번호) → 토큰을 메모리에 두고 모든 `fetch` 에 Bearer. `DEBUG=1` 에서만 뜨는 개발 페이지.

### 4.4 CLI (`app/cli.py`, `uv run python -m app.cli …`)

```
create-school --name 우송대 --net-id 75 --email-domain wsu.ac.kr
update-school --id 1 [--name …] [--net-id …] [--email-domain …]
create-admin  --school-id 1 --email admin@wsu.ac.kr --name 관리자   # 비밀번호는 getpass 로(argv 에 안 남게), 8자 미만 거부. 같은 email 있으면 오류
set-user      --email admin@wsu.ac.kr [--status active|disabled] [--password]   # 관리자 복구·정지, token_version+1
assign-modem  --modem-id m2 --school-id 1          # school_id 가 NULL 로 고립된 모뎀 복구
```

실행은 `.env` 를 읽은 환경에서: `uv run --env-file .env python -m app.cli …` (서버 기동도 `uv run --env-file .env uvicorn …`).

## 5. 영역별 영향

- `server/app/auth/` (신규): `models.py`(User, EmailToken) · `password.py`(hash/verify) · `tokens.py`(메일 토큰 issue/consume, JWT encode/decode) · `mailer.py`(send + 템플릿 3개) · `deps.py`(가드·스코프 헬퍼) · `router.py`(§4.1·4.2) · `ratelimit.py`.
- `server/app/cli.py` (신규), `server/alembic/versions/web_auth_<rev>.py`.
- `server/app/settings.py`: §6 키. `server/app/main.py`: `DEBUG` 조건 마운트, CORS, 전역 500 핸들러, 라우터 등록.
- `server/app/domain/router.py`, `server/app/lora_service/router.py`: 가드·`_get_scoped`·목록 필터·PATCH 부분 수정·건물 `modem_id`·`bld` 검사. **`lora_service/api.py`·`hub.py` 불변.** `lora_service/models.py` 에 `Modem.school_id` 컬럼 1개(라우터 스코프 전용 — cw 리뷰).
- `server/app/db.py`: 엔진 `hide_parameters=True`.
- `server/app/domain/csv_import.py`: `parse(text, s, school_id=)` — 조회를 그 학교로 한정.
- `server/app/schemas.py`: `UserOut`, auth 요청 모델, `RoomIn.reservable`, `ModemOut.school_id`.
- `server/tests/conftest.py`: 관리자 시드 + Bearer 자동 첨부 `client`. 기존 S2·S2b 테스트는 호출부 불변.
- `server/README.md`, `.env.example`(신규, 값 비움).
- modempi·firmware·`lora_proto`: 영향 없음. web: S4·S10 화면이 `/api/auth/*` 를 쓴다(후속).
- 로드맵 §4 계약 ⑤ "REST = OpenAPI" 에 인증 등급이 추가됨 — PR 본문에 cw 반영 요청.

## 6. 설정 (`.env`)

| 키 | 필수 | 기본 | 용도 |
|---|---|---|---|
| `JWT_SECRET` | ✅ | — | 없거나 32자 미만이면 기동 실패 |
| `STUDENT_WEB_URL` | ✅ | — | 메일 링크 prefix (예 `https://rooms.wsu.ac.kr`) |
| `SMTP_USER`, `SMTP_PASSWORD` | `MAIL_BACKEND=smtp` 면 ✅ | — | Gmail 계정 + **앱 비밀번호**(2단계 인증 필요) |
| `MAIL_FROM` | | `SMTP_USER` | 발신 표시 |
| `MAIL_BACKEND` | | `smtp` | `smtp` \| `console`(stdout, 개발·테스트 — 메일 토큰이 로그에 남으므로 `DEBUG=1` 필요, 아니면 기동 실패) |
| `DEBUG` | | `0` | `1` 이면 `/docs`·`/openapi.json`·`/static` |
| `CORS_ORIGINS` | | 빈 값 | 쉼표 구분 허용 origin |
| `JWT_TTL_H` | | `24` | |

메일: `smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)` + `email.message.EmailMessage`. 인터페이스 `send(to, subject, body, kind)` 하나(`kind` = verify·reset·decision, 종류별 상한 §3.4). 템플릿은 f-string 함수 3개(인증·재설정·승인/거절). 호출은 **핸들러가 `s.commit()` 한 뒤** `BackgroundTasks` 로(§3.4), 실패는 `log.exception` 만 — 승인 메일이 실패해도 승인은 유효하고 학생은 로그인할 수 있다.

## 7. 무회귀 · 롤아웃

- 마이그레이션 additive(테이블 2 + 컬럼 3). 기존 `buildings.bld` 가 학교 간에 겹치면 마이그레이션이 실패하도록 사전 검사(전시 규모엔 없음 — 있으면 수동 정리 후 재실행). 기존 행 영향 없음(`reservable` 0, `modems.school_id` NULL → 관리자가 다음 등록/배정 때 채워짐. 기존 모뎀은 CLI 없이 `PATCH /api/lora/modems/{id}`… 은 없으므로 **마이그레이션에서 `buildings.modem_id` 로 역추적해 채운다**).
- 기존 테스트 전부 통과(conftest 관리자 Bearer). 테스트 수 유지 + 아래 추가.
- 테스트(전부 `TestClient`, `mailer.send` monkeypatch 로 캡처, `clock` 주입):
  - 가입: 이메일 형식(쉼표·두 개의 `@`·공백·꺾쇠) 422 / 도메인 불일치 400 / 정상 202 + 메일 캡처, **DB 에 users 행 없음** / 이미 가입된 email 202·메일 없음 / 60 s 이내 재신청 메일 없음
  - 링크: verify(이름·학번·비번) 성공 → `pending_approval` / 재사용 400 / 5 분 안에 안 열면 400 / **4 분에 열고 25 분에 제출 200**, 여러 번 열어도 발급 + 35 분 상한 / 재발급해도 먼저 연 링크는 유효, 성공 뒤엔 전부 무효 / 주소당 시간 3통 / 비번 7자 422 / 같은 학교 학번 중복 409 → 학번 고쳐 같은 토큰 200 / 학번 조회 6번째 429 / **선점 시나리오**: 공격자가 먼저 signup 해도 행이 없어 피해자 verify 가 피해자 비밀번호로 생성 / **거절 행**: 같은 학번으로 다른 사람 가입 가능, 거절된 본인 재신청 가능
  - 상한: 메일 종류별(verify 상한을 다 써도 reset·decision 발송) / 가입 도메인 상한 429(다른 학교는 별도) / 레이트리밋 하루 창 키가 1 분 뒤 정리에도 유지
  - 로그인: 상태별(pending_approval 403, active 200, disabled 401, rejected 401) / 비번 틀림 401 / 없는 email 401 / JWT 클레임(`tv`) / 만료 토큰 401 / disabled 즉시 401
  - 재설정: forgot 202(없는 email 도 202) / reset 후 옛 비번 401·새 비번 200 / 토큰 1회용 / **reset 전에 받은 JWT 401**(token_version)
  - 커밋 순서: 메일 캡처 콜백 안에서 새 세션으로 조회하면 이미 커밋돼 있다
  - 관리자: approve·reject·disable·enable 전이와 409 / 타 학교 사용자 404 / 학생 토큰으로 관리자 API 403 / 관리자 자신 disable 400
  - 스코프: 관리자 A 가 학교 B 의 건물·강의실·슬롯·모뎀·outbox·status·pending → 404 또는 목록 제외 / CSV `school` 불일치 행 오류(이름을 맞춰도) / 모뎀 등록 시 `school_id` 채워짐 / 건물에 타교 모뎀 404 / 타교가 쓰는 bld 409 / provision 목표 방 타교 404 / PATCH 부분 수정으로 `reservable` 유지 / `/api/lora/time` 두 번째 429
  - 마이그레이션: `upgrade head` 뒤 `alembic_version` 이 채워져 있다(조용한 롤백 감지 — env.py 에서 연결에 SQL 을 먼저 실행하면 전체가 롤백된다, r3) / 부분 유일 인덱스(거절 행 제외)
  - 노출 면적: `DEBUG=0` 에서 `/docs`·`/openapi.json`·`/static/index.html` 404, `DEBUG=1` 200 / `/api/health` 본문 == `{"ok": true}` / 500 본문에 예외 문자열 없음 / 응답 JSON 어디에도 `pw_hash`·`token_hash` 없음 / 6번째 로그인 시도 429 / CORS 미허용 origin 에 `Access-Control-Allow-Origin` 없음 / `JWT_SECRET` 31자 기동 실패 / IntegrityError 로그에 파라미터 없음
  - CLI: `create-school`·`update-school`·`create-admin`(getpass, 7자 거부) → 로그인 가능, 중복 오류

## 8. 성공 기준

- `.env` 에 Gmail 앱 비밀번호를 넣고 실제 웹메일로 가입 → 5 분 안에 링크 클릭 → 이름·학번·비밀번호 입력 → 관리자 승인 → 로그인 → `GET /api/auth/me` 가 학생 정보를 돌려준다.
- 관리자 A 토큰으로 학교 B 의 강의실 id 를 찍으면 404, 목록에도 없다.
- 새 DB 에 `alembic upgrade head` → `alembic_version` 이 head, 모든 테이블이 있다.
- `DEBUG` 없이 기동한 서버에서 `/docs` 404, `/api/health` 는 `{"ok": true}` 8바이트.
- 기존 S2·S2b 테스트 전부 통과.

## 9. 열린 결정 (plan 단계에서 확정)

- 브루트포스 카운터의 키를 email 만 할지 email+IP 로 할지 — 단일 워커·리버스 프록시 뒤라 IP 신뢰가 애매해 email 만.
- `modems.school_id` 마이그레이션 역추적: 건물 미배정 모뎀은 NULL 로 남는다 → 어느 관리자 목록에도 안 보임 → CLI `assign-modem` 으로 붙인다.
- 이메일 정규식은 RFC 5322 전체가 아니라 학교 웹메일이 실제로 쓰는 형식만. 따옴표 로컬파트 등은 거부된다 — 의도.
- 승인·거절 메일 문구 — 최소(한 줄 + 사유). 화면 스펙(mh) 오면 다듬음.
