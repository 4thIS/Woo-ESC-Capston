# S2 — 메인Pi 서버: 통신 뼈대 + 최소 도메인 — 설계 (spec)

- 생성일시: 2026-09-14
- 수정일시: 2026-09-14
- 상위 문서: `2026-09-09-roadmap-design.md` §3(책임 분할)·§4.2(계약 ⑥ WS 백홀)·§4.5(v2 §8 개정)·§7.1(지연 예산). `api.py` 시그니처·테이블·버전 규칙 원본은 `2026-09-09-lora-v2-wor-design.md` §8.2·8.3·8.6·8.7. 모뎀Pi 쪽 상대는 `2026-09-10-s6-modempi-lora-pipeline-design.md`(§5 "server 영향").
- 담당: wj @leemonta9482. 영역 `server/`. `server/app/lora_service/`는 cw @ssenu 필수 리뷰.

## 0. 배경 · 위치

`server/`는 비어 있다. 4주차 Pi↔Pi 통합(로드맵 §7 "메인Pi 웹 저장 → 모뎀Pi fake 모뎀 → `job_result` → 대시보드 acked")까지 메인Pi가 **계약 ⑥의 제공자**로 서 있어야 하고, S5 링크(모뎀Pi)는 이 서버의 `fake_hub.py`로 테스트한다. 이 문서는 그 통신 뼈대와, 뼈대를 실제로 돌려 보는 데 필요한 최소 도메인만 다룬다. 화면 디자인·사용자 인증은 다루지 않는다(후속 spec).

v2 §8은 웹서버와 모뎀이 한 호스트라는 전제로 쓰였고, 로드맵 §4.5가 워커·codec을 모뎀Pi로 옮겼다. 이 문서는 그 개정을 메인Pi 코드 구조로 확정한다.

## 1. 목표 · 비목표

### 목표
- 계약 ⑥(WS 백홀) 메시지 10종을 그대로 제공하는 허브. 모뎀Pi가 `hello`로 붙으면 `config`와 밀린 `queued`가 나가고, `job_accepted`/`job_result`/`uplink`가 DB에 반영된다.
- v2 §8.6 `api.py` 시그니처 그대로. **버전 +1과 outbox 삽입이 한 트랜잭션**, `unit=0`은 유닛별 행으로 분해, 255→1 롤링, GAP·버전 불일치 시 FILE 재동기 큐잉(중복 금지).
- 저장→허브 송신 지연 ≤ 0.1 s(로드맵 §7.1). 재접속해도 `dispatched`는 재전송하지 않는다(중복 송신 0).
- 최소 도메인(학교→건물→강의실, 시간표·예약·시험기간)의 REST. 변경하면 outbox에 작업이 생긴다.
- Swagger `/docs`와 무스타일 정적 HTML 1장으로 통신 루프를 눈으로 확인한다.
- `server/tests/fake_hub.py` — S5 링크 테스트가 재사용하는 최소 WS 서버.

### 비목표 (이번엔 안 함 / 후속)
- 사용자·로그인·JWT·RBAC. 기획 미확정. 라우터는 나중에 인증 의존성을 앞에 붙일 수 있는 형태로만 둔다. (모뎀Pi 토큰은 사용자 인증이 아니라 계약 ⑥ `hello.token`이므로 포함한다.)
- CSV 임포트, 학생 웹 API, 대시보드 집계(갱신 지연 히스토그램 등) — S4·S10.
- 무선 파라미터 오버라이드 컬럼(`config.radio`는 `lora_proto.proto.RADIO` 기본값 그대로). P0 SF 실측 후 additive.
- 실패 작업 04:00 재큐잉(S6 §5가 메인Pi로 넘긴 것). 다음 spec에 명시적으로 남긴다.
- 화면 디자인. `static/index.html`은 스타일 0줄.
- Vue `web/`의 화면. 스캐폴드(wj-01)는 이 spec과 별개로 빈 뼈대만 만든다(mh-01 착수 조건).

## 2. 데이터 · 계약

- `lora_proto/` 프로토콜 정의 변경: **아니오**. `proto.RADIO`·`Type`·`codec` dataclass를 소비만 한다.
- DB 스키마·마이그레이션 변경: **예** (신규). Alembic, `lora_*`(cw 리뷰)·`web_*` 두 계열. 마이그레이션이 그 컬럼을 쓰는 코드보다 먼저 머지된다.
- 서버 응답 스키마(웹이 소비) 변경: **예** (신규). 이후 변경은 additive.
- 계약 ⑥ 변경: **아니오**. 로드맵 §4.2 표 그대로. 이 spec이 정하는 것은 그 표의 **구현 규칙**(§3·§4)뿐이다.
- 계약 ⑦ `JobStore`: 이 영역은 모른다. `job.payload`의 키가 `lora_proto.codec` dataclass 필드명과 같다는 S6 §4.2 규칙을 서버가 지킨다.

### 2.1 DB — SQLite

파일 하나(`SERVER_DB=/var/lib/roomsign/main.db`), WAL, `busy_timeout=5000`. SQLAlchemy 2.x + Alembic. 테스트는 임시 파일(실물 사용, mock 아님). Postgres는 URL만 바꾸면 되도록 방언 특화 기능을 쓰지 않는다.

### 2.2 도메인 테이블 (`web_` 마이그레이션)

| 테이블 | 컬럼 | 비고 |
|---|---|---|
| `schools` | `id`, `name`, `net_id` u8 UNIQUE | NET_ID는 학교 단위(로드맵 §3) |
| `buildings` | `id`, `school_id`, `name`, `bld` CHAR(1), `modem_id` → `modems` NULL. UNIQUE(`school_id`,`bld`) | 건물 1 = 모뎀Pi 1. `bld`는 헤더 BLD 바이트(ASCII) |
| `rooms` | `id`, `building_id`, `room` u16(1~9999), `units` u8 ∈ {1,2}. UNIQUE(`building_id`,`room`) | `units`가 유닛 분해 근거 |
| `slots` | `id`, `room_id`, `day` 1~7, `s_h`,`s_m`,`e_h`,`e_m`, `type` 1~6, `subject`(UTF-8 ≤ 20 B), `professor`(≤ 12 B). UNIQUE(`room_id`,`day`,`s_h`,`s_m`) | = SLOT_SET 페이로드. 멱등키 = 노드와 동일 |
| `reservations` | `id`(= resvId, `CHECK(id BETWEEN 1 AND 65535)`), `room_id`, `date`, `s_h`,`s_m`,`e_h`,`e_m`, `type`, `subject`, `professor` | = RESV_SET |
| `exam_periods` | `id`(= examId, u16), `room_id`, `date_start`, `date_end` | = EXAM_SET, 양끝 포함 |

문자열 한계는 `lora_proto.proto.SUBJ_MAX`·`PROF_MAX`를 참조한다(재정의 금지).

### 2.3 lora_service 테이블 (`lora_` 마이그레이션, cw 리뷰)

v2 §8.2를 로드맵 §4.5로 개정한 것.

| 테이블 | v2 대비 변경 |
|---|---|
| `outbox` | `state ∈ queued\|dispatched\|acked\|failed\|cancelled` (**`sending` 없음** — 모뎀Pi 상태). 추가: `modem_id`, `dispatched_at`, `finished_at`, 결과 필드 `ack_status, ack_detail, attempts, txn, rssi, snr, batt_mv, layout, fw, sched_ver, resv_ver, exam_ver, ident_ver, last_error`. `priority`: 0 TIME, 1 RESV, 3 SLOT/EXAM/CMD/SET_ROOM, 5 FILE |
| `modems` | 신규. `modem_id` TEXT PK(예 `"mjc-eng"`), `token_hash`(sha256 hex), `agent_ver`, `modem_fw`, `last_seen_at`, `connected` bool. net_id·radio는 **저장하지 않고** `buildings→schools` 조인과 `proto.RADIO`에서 만든다(단일 진실원) |
| `room_versions` | 그대로. PK(`bld`,`room`,`kind`), `ver` 1~255 |
| `terminal_status` | 그대로 + `modem_id` |
| `pending_devices` | 그대로 + `modem_id`(어느 모뎀Pi가 HELLO를 들었는가) |
| `lora_log` | 그대로. 허브가 송수신 메시지를 1행씩 |

### 2.4 계약 ⑥ 구현 규칙

로드맵 §4.2 표가 형태를, 여기가 동작을 정한다.

| 시점 | 규칙 |
|---|---|
| 접속 | `WS /ws/modem`. 첫 메시지는 10 s 안에 `hello`. 아니면 close |
| `hello` | `modems.modem_id` 존재 + `sha256(token) == token_hash`. 아니면 close(4001). 같은 `modem_id`가 이미 연결돼 있으면 **이전 연결을 닫고 교체**. `last_seen_at/connected/agent_ver/modem_fw` 갱신 → `config` 송신 → 그 모뎀의 `queued` 전부를 `job`으로 송신 |
| `config` 내용 | `net_id` = 건물의 학교, `radio` = `proto.RADIO`에서 `{sf,bw,cr,tx_dbm,preamble_wake_ms}`, `nodes` = 그 건물 `rooms` × `units` → `[{bld,room,unit}]`, `qr_base_url` = 설정값(빈 문자열 가능), `status_hour_utc` = 설정값(기본 18 = KST 03:00) |
| `job` 송신 | outbox 행 → `{t:"job", job_id, bld, room, unit, type, payload, priority, new_ver}`. `payload` 키 = codec 필드명에서 `new_ver` 제외(`new_ver`는 job 필드). `bytes` 필드(`mac`, `args`)는 **hex 문자열**. FILE은 `{"kind": 1\|2\|3, "records": [레코드 dict…]}`. 송신했다고 상태를 바꾸지 않는다 |
| `job_accepted` | `queued → dispatched`, `dispatched_at`. 이미 `dispatched` 이상이면 무시(멱등) |
| `job_result` | `api.on_job_result()`에 위임. `dispatched → acked\|failed` + 결과 필드 + `finished_at`. `terminal_status` 갱신. 이미 끝난 행이면 로그만(모뎀Pi 재전송) |
| `uplink` | `api.on_uplink()`에 위임. STATUS → `terminal_status` + 버전 비교, HELLO → `pending_devices` upsert |
| `cancel` | `api.cancel()`이 `queued → cancelled`. 행이 `dispatched`면 DB는 그대로 두고 모뎀에 `cancel` 송신 — 모뎀Pi가 아직 `received`면 `job_result(failed, cancelled)`로 돌아온다 |
| `time_now` | `POST /api/lora/time` → 연결된 모든 모뎀에 송신. outbox 행 없음(TIME 결과는 메인이 안 봄) |
| `ping`/`pong` | 서버가 30 s마다 `ping`. `pong` 2회 연속 없음 → close |
| 끊김 | `connected=false`. 연결 레지스트리는 프로세스 메모리(`modem_id → WebSocket`). 재기동 시 모뎀Pi 재접속으로 복구되므로 영속화하지 않는다 |
| 안전망 태스크 (5 s) | 연결된 모뎀의 `queued`를 flush(notify 유실 대비). `last_seen_at`이 24 h 이전인 모뎀의 `dispatched`를 `failed(last_error="modem_offline")` |

### 2.5 디스패치 — notify + hello flush + 안전망

`api.py`는 동기 함수(웹 요청 스레드)이고 허브는 asyncio다. `api.enqueue_*`가 커밋한 뒤 `notify(modem_id)`를 부르고, 허브는 이를 `loop.call_soon_threadsafe`로 받아 그 모뎀의 `queued`를 flush한다. `notify`는 허브가 기동 시 `api.set_notify(fn)`으로 **주입**한다 — `api.py`는 허브를 import하지 않는다. 폴링(1 s)은 §7.1 예산을 어기므로 주 경로가 아니고, 5 s 안전망으로만 남는다.

## 3. 접근 제어 / 제약

- 사용자 인증 없음(비목표). 모든 `/api/*`는 열려 있다. 인증 spec이 오면 라우터 `dependencies=[...]` 한 줄로 붙인다.
- 모뎀Pi 토큰: `POST /api/lora/modems` 응답에 평문 토큰을 **1회** 돌려주고 DB에는 sha256만. 재발급은 같은 엔드포인트 `POST …/{modem_id}/token`.
- 검증은 Pydantic에서 한 번, `api.py`에서 codec dataclass(`C.SlotSet(...)` 등)를 **실제로 만들어** 한 번 더. 두 번째가 실패하면 400 — 모뎀Pi에서 `bad_payload`로 죽을 작업을 서버에서 막는다.
- 문자열 길이는 **UTF-8 바이트** 기준(`proto.SUBJ_MAX=20`, `PROF_MAX=12`). 화면 표시 한계와 같다(v2 §5.1).
- 예약은 `date`가 오늘~7일 이내인 것만 outbox로 보낸다(v2 §12 슬롯 24개 억제). 그 밖은 저장만.
- `on_job_result`의 버전 비교: ACK의 `sched_ver/resv_ver/exam_ver`가 `room_versions`와 다르거나 `ack_status=GAP`이면 `terminal_status.sync_state='resync'` + 해당 kind FILE 큐잉. 같은 (bld,room,unit,kind)에 `queued|dispatched` FILE이 있으면 큐잉하지 않는다.
- FILE 작업은 삽입 시점에 `RecordProvider(bld, room, kind)`로 레코드를 읽어 `payload.records`에 **통째로** 넣는다(로드맵 §4.2). 모뎀Pi는 사본을 갖지 않는다.
- `unit=0` 요청은 `rooms.units`만큼 행으로 분해하고 같은 `NEW_VER`를 준다. 분해된 행 각각이 독립적으로 `acked|failed`.
- 도메인 의존 방향: `domain → lora_service.api` 단방향. `lora_service`는 `domain`을 import하지 않는다(레코드는 `RecordProvider` 콜백). `hub → api` 단방향, `api → hub`는 주입된 `notify`만.
- 지연 예산(로드맵 §7.1): 저장 응답 → `job` 송신 ≤ 0.1 s. 측정 기준점 `outbox.created_at`은 저장 트랜잭션 커밋 시각.

## 4. 인터페이스 계약

### 4.1 모듈 (`server/`)

```
server/
├── pyproject.toml          # uv. fastapi, uvicorn, sqlalchemy, alembic, pydantic, lora-proto(path); dev: pytest, httpx, websockets, ruff
├── app/
│   ├── main.py             # 앱 생성, lifespan(허브·안전망 태스크), /static, set_record_provider·set_notify 1회
│   ├── db.py               # engine·Session·get_db
│   ├── settings.py         # SERVER_DB, QR_BASE_URL, STATUS_HOUR_UTC (env)
│   ├── domain/
│   │   ├── models.py       # §2.2
│   │   ├── records.py      # RecordProvider 구현
│   │   └── router.py       # §4.3 도메인 REST
│   └── lora_service/       # 보호 계층
│       ├── models.py       # §2.3
│       ├── api.py          # §4.2
│       ├── hub.py          # §2.4·2.5
│       └── router.py       # §4.3 /api/lora/*
├── static/index.html
├── alembic/
└── tests/  (fake_hub.py, test_api.py, test_hub.py, test_domain.py)
```

### 4.2 `lora_service/api.py` (v2 §8.6 + 추가 3개)

모두 동기, 자체 세션, 한 트랜잭션. 웹 라우터는 이 파일과 `set_record_provider`만 import한다.

| 함수 | 비고 |
|---|---|
| `enqueue_slot_set(bld, room, day, start, end, type_, subject, professor, unit=0) -> list[int]` | v2 그대로. 반환 = outbox ids |
| `enqueue_slot_del`, `enqueue_day_clear`, `enqueue_resv_set`, `enqueue_resv_del`, `enqueue_exam_set`, `enqueue_exam_del`, `enqueue_full_sync`, `enqueue_cmd` | v2 §8.6 시그니처 그대로 |
| `provision(mac, bld, room, unit) -> int` | `room_versions[ident]` +1 → SET_ROOM 행 삽입(outbox 주소 = 배정할 방; BLD=0x00 헤더는 모뎀Pi 전처리 몫). `config.nodes`는 rooms에서 나오므로 재송 없음. `pending_devices` 행은 그 SET_ROOM이 `acked`로 돌아올 때 `on_job_result`가 삭제한다(v2 §7) |
| `request_time_broadcast() -> int` | 연결 모뎀에 `time_now`. 반환 = 송신한 모뎀 수 |
| `get_status(bld=None, room=None)`, `get_pending_devices()`, `get_outbox(state=None, bld=None, room=None, limit=100)`, `cancel(outbox_id) -> bool` | v2 그대로 |
| `set_record_provider(fn)` | v2 §8.7. `fn(bld, room, kind) -> list[codec dataclass]` |
| **`set_topology(t)`** | 추가. 같은 원리(lora_service는 domain을 import하지 않음). `t.room(bld, room) -> RoomInfo(modem_id, units, net_id) \| None`, `t.nodes(modem_id) -> [(bld, room, unit)]`, `t.net_id(modem_id)`. domain이 구현해 기동 시 주입 |
| **`set_hub(port)`** | 추가. 허브가 주입하는 단일 포트: `notify(modem_id)`, `config_changed(modem_id)`, `time_now() -> int`, `cancel(modem_id, job_id)`. §2.5의 `set_notify`는 이 포트에 흡수 |
| **`on_job_result(modem_id, msg: dict)`** | 추가. 허브가 부름. §2.4 `job_result` 규칙 |
| **`on_uplink(modem_id, msg: dict)`** | 추가. 허브가 부름. §2.4 `uplink` 규칙 |
| **`register_modem(modem_id) -> str`**, **`rotate_token(modem_id) -> str`** | 추가. 평문 토큰 반환(1회) |

### 4.3 REST

| 메서드·경로 | 접근 | 설명 → outbox |
|---|---|---|
| `GET/POST /api/schools`, `PATCH/DELETE /api/schools/{id}` | (인증 없음) | CRUD |
| `GET/POST /api/buildings`, `PATCH/DELETE …/{id}` | | CRUD. `modem_id` 변경 시 관련 모뎀에 `config` 재송 |
| `GET/POST /api/rooms`, `PATCH/DELETE …/{id}` | | CRUD. 생성·`units` 변경·삭제 시 `config` 재송 |
| `GET /api/rooms/{id}/slots` | | 목록 |
| `PUT /api/rooms/{id}/slots` | | upsert(멱등키 day,s_h,s_m) → `enqueue_slot_set`. 응답에 `outbox_ids` |
| `DELETE /api/rooms/{id}/slots/{day}/{s_h}/{s_m}` | | → `enqueue_slot_del` |
| `DELETE /api/rooms/{id}/slots?day=N` | | → `enqueue_day_clear` |
| `GET/POST /api/rooms/{id}/reservations`, `DELETE …/{resv_id}` | | → `enqueue_resv_set/del` |
| `GET/POST /api/rooms/{id}/exams`, `DELETE …/{exam_id}` | | → `enqueue_exam_set/del` |
| `POST /api/rooms/{id}/sync` (body: kinds) | | → `enqueue_full_sync` |
| `POST /api/rooms/{id}/cmd` (body: cmd, args) | | → `enqueue_cmd` |
| `GET /api/lora/modems`, `POST /api/lora/modems` | | 등록(평문 토큰 1회), 목록 + `connected`·`last_seen_at` |
| `POST /api/lora/modems/{modem_id}/token` | | 토큰 재발급 |
| `GET /api/lora/outbox?state=&bld=&room=&limit=` | | `get_outbox` |
| `POST /api/lora/outbox/{id}/cancel` | | `cancel` |
| `GET /api/lora/status`, `GET /api/lora/pending` | | `get_status`, `get_pending_devices` |
| `POST /api/lora/pending/{mac}/provision` (bld, room, unit) | | `provision` |
| `POST /api/lora/time` | | `request_time_broadcast` |
| `WS /ws/modem` | 모뎀 토큰 | 계약 ⑥ |
| `GET /static/index.html`, `GET /docs` | | 확인용 |

응답 스키마는 Pydantic 모델 한 벌(`app/schemas.py`)로 고정. 이후 필드 추가는 additive.

### 4.4 `static/index.html`

스타일 0줄. ① `GET /api/lora/modems` 표 ② 시간표 저장 폼(`PUT /api/rooms/{id}/slots`) ③ `GET /api/lora/outbox` 표(state·attempts·ack_status·finished_at), 2 s마다 갱신. 이 이상 넣지 않는다 — 통신 루프 확인이 목적이고 화면은 후속 spec.

### 4.5 `tests/fake_hub.py`

`websockets` 라이브러리로 뜨는 최소 서버. DB 없음. `hello` 검증(고정 토큰) → `config` → 테스트가 넣어 준 `job` 목록 송신 → `job_accepted`/`job_result`/`uplink`를 리스트에 기록. `ping`에 `pong`. S5 링크 테스트(`modempi/tests/`)가 import하므로 시그니처(`FakeHub(token, jobs) → .received`)는 additive로만 바꾼다.

## 5. 영역별 영향

- server: 이 문서 전부(신규).
- modempi (S5 링크, wj): `server/tests/fake_hub.py`를 재사용. `job.payload` 키 = codec 필드명 확인. `cancel`이 `dispatched` 행에 와도 처리(§2.4).
- modempi (S6 파이프라인, cw): 영향 없음. S6 §5가 요구한 "04:00 실패 재큐잉을 메인Pi 규칙으로"는 후속 spec.
- web: 이번엔 소비하지 않음. `web/` 스캐폴드는 별도(wj-01).
- lora_proto: 없음. `proto.RADIO`·`SUBJ_MAX`·`PROF_MAX`·`Type`·`codec` dataclass 소비.
- firmware: 없음.

## 6. 무회귀 · 롤아웃

- 기존 코드 없음 → 회귀 대상 없음. 계약 ⑥ 형태는 로드맵 §4.2와 바이트 단위로 같아야 하며 `test_hub.py`가 메시지 10종의 키를 고정한다.
- 머지 순서: ① 스캐폴드(pyproject·CI 켜짐) → ② `lora_` 마이그레이션 + `lora_service`(cw 리뷰) → ③ `web_` 마이그레이션 + domain → ④ hub → ⑤ static. 각각 PR 1개.
- 4주차 통합에서 모뎀Pi 링크(S5)가 이 허브에 붙는다. 그 전까지는 `test_hub.py`의 fake 링크가 상대.

## 7. 역할 분담

| 영역 | 담당 |
|------|------|
| `server/app/domain/`, `static/`, `tests/` | wj @leemonta9482 |
| `server/app/lora_service/` 구현 | wj @leemonta9482 (cw @ssenu 필수 리뷰) |
| `lora_` 마이그레이션 리뷰 | cw @ssenu |
| `fake_hub.py` 인터페이스 합의 | wj (S5도 wj) |

## 8. 성공 기준

- `uv run pytest` 녹색, CI `server` job 녹색. ruff 통과.
- `test_api.py`: 버전 +1과 outbox 삽입이 한 트랜잭션(중간 예외 → 둘 다 롤백) / `unit=0` → 행 2개·같은 NEW_VER / 255→1 롤오버 / GAP → FILE 1건만 / 24 h 오프라인 → `failed(modem_offline)`.
- `test_hub.py`: 토큰 불일치 close / hello → config 수신(`nodes` = rooms×units) / `queued` → `job` 수신 → `job_accepted` → `dispatched` / 끊고 재접속 → `dispatched` 재전송 0건, `queued`만 재송 / `job_result` → `acked` + `terminal_status` / `uplink HELLO` → `pending_devices`.
- `test_domain.py`: `PUT slots` → outbox 행 1개(units=1) 또는 2개(units=2), `C.SlotSet(**payload)`가 성립.
- 수동: `uvicorn` 띄우고 `/static/index.html`에서 시간표 저장 → outbox 표에 `queued` → (fake 링크 붙이면) `dispatched` → `acked`.
- 지연: 저장 응답 시각과 `job` 송신 로그 시각 차 ≤ 0.1 s(로컬).

## 9. 열린 결정 (plan 단계에서 확정)

- `STATUS_HOUR_UTC` 기본값 18(KST 03:00, v2 §8.4)로 두되 env로 바꿀 수 있게 — 확정 필요 없음, 기록만.
- `cancel`이 `dispatched` 행에 왔을 때 DB를 `cancelled`로 먼저 바꿀지, 모뎀Pi `job_result`를 기다릴지. 이 spec은 "기다린다"(§2.4)로 두었다. S5 spec에서 모뎀Pi 쪽 처리를 정할 때 다시 본다.
- `reservations.id`를 u16 resvId로 직접 쓰면 65535개 이후 재사용 문제 — 캡스톤 규모에서는 무시. 초과 시 별도 `resv_id` 컬럼으로 롤링(additive).
- 실패 작업 재큐잉 규칙(04:00) — 후속 spec. 이번엔 `failed`를 대시보드에 노출만.
