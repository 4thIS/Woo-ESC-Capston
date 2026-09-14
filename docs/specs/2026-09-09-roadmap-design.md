# 진행 로드맵 · 3계층 토폴로지 · 서브프로젝트 분해 · 영역 간 계약 — 설계 (spec)

- 생성일시: 2026-09-09
- 수정일시: 2026-09-09 (r2 — 메인Pi/모뎀Pi/ESP노드 3계층 토폴로지 반영, 모뎀Pi 내부를 링크/파이프라인으로 분할)
- 상위 문서: `docs/specs/2026-09-09-lora-v2-wor-design.md` (v2 시스템 설계). 공중 프로토콜(§2·§3)·모뎀 펌웨어(§4)·ESP노드 펌웨어(§5~7)는 그 문서가 원본이다. **v2 §8(백엔드 LoRa 서비스)은 이 문서 §4로 대체한다** — 워커·modem.py·codec이 모뎀Pi로 이동했다.
- 근거 문서: 과제추진계획서(Woo팀), 2026-2 캡스톤디자인 운영계획

## 0. 배경 · 위치

v2 설계 스펙은 여러 서브시스템을 다루며 한 번에 구현할 크기가 아니다. 규율 뼈대(CLAUDE.md·CODEOWNERS·CI)는 갖춰졌고 코드는 아직 없다. 팀 협의로 **여러 학교·여러 건물을 한 웹서버가 서비스하는 3계층 토폴로지**가 확정되어, v2 §8이 전제한 "웹 서버와 LoRa 모뎀이 한 호스트"가 더 이상 성립하지 않는다. 이 문서는 첫 코드를 쓰기 전에 다음을 확정한다.

1. 세 장비(메인Pi·모뎀Pi·ESP노드)의 책임과 그 사이의 계약
2. 전체를 어떤 서브프로젝트로 쪼개고 누가 어떤 순서로 가는가
3. 하드웨어가 없는 첫 3주에 무엇을 만드는가
4. 각 마일스톤에서 무엇을 어떤 수치로 보여주는가

### 장비 명칭 (이 이름만 쓴다)

| 이름 | 실체 | 수량 |
|---|---|---|
| **메인Pi** | Raspberry Pi (보유). 인터넷에서 닿는 곳. 웹서버·DB 원본 | 전체 1대 |
| **모뎀Pi** | Raspberry Pi (보유) + Heltec V3 모뎀(USB). 학교 건물당 1대, 학교 내부망(NAT) 안 | 건물당 1대 |
| **ESP노드** | Heltec V3 + 7.5" e-Paper + LiPo. 강의실 문마다 | 강의실당 1~2대(앞문·뒷문) |

Heltec V3에 올라가는 두 펌웨어는 각각 **모뎀 펌웨어**(모뎀Pi에 USB로 붙는 것, v2 §4)와 **노드 펌웨어**(ESP노드, v2 §5~7)라 부른다.

### 확정된 제약

| 항목 | 값 |
|---|---|
| 오늘 | 2주차 (2026-09-09, 수요일 수업) |
| 하드웨어 | Pi 2대 **보유**. Heltec V3·e-Paper·배터리는 **미발주** → 도착 예상 5주차(10월 초) |
| 철석 마감 | **경진대회 2026-11-19~20 (12주차)** — 참가신청서·작품보고서·판넬 + 동작 전시 |
| 중간점검 | 7~8주차 |
| 최종발표 | 15주차 (12월 초). 과제 시행 ~12/14, 결과보고 12/8~12/21 |
| 범위 | 계획서 전체 **− 재실 감지 센서**. 학사 연동은 **관리자 CSV 업로드** |
| 전시 규모 | 메인Pi 1 + 모뎀Pi 1 + ESP노드 **2** |
| 팀 | cw @ssenu (PM, 프로토콜·LoRa 파이프라인·노드 펌웨어) · dh @Hyeon02-kr (e-Paper 렌더, 모뎀 펌웨어 지원) · wj @leemonta9482 (메인Pi 서버·웹·모뎀Pi 링크) · mh @jmh7706jmh-ops (웹 퍼블리싱) |

## 1. 목표 · 비목표

### 목표
- 경진대회(12주차)에 **웹 수정 → 메인Pi → 인터넷 → 모뎀Pi → LoRa → ESP노드 e-Paper 갱신** 루프가 ESP노드 2대·배터리 구동·절전 모드로 동작하고, 관리자 웹·학생 웹·분석 대시보드가 함께 전시된다.
- 중간점검(7~8주차)에 같은 루프가 ESP노드 1대·깨어있는 모드로 시연된다.
- 하드웨어가 없는 2~4주차에 네 사람 모두가 실제 코드를 쓴다. 특히 모뎀Pi 소프트웨어는 **Pi 2대가 이미 있으므로 4주차에 실기(Pi↔Pi)로 통합**한다.
- 최종발표(15주차)에 전력 실측(v2 §1.4 대비)과 1주 소크 결과를 표로 제시한다.

### 비목표 (이번엔 안 함 / 후속)
- 재실 감지 센서 및 실제 점유 측정. "점유율"은 **시간표·예약 기반 배정률**과 노드 상태 변화 로그로 정의한다.
- 학사포털·LMS 직접 연동. CSV 업로드가 유일한 입력 경로.
- 모뎀Pi에 시간표 사본 보관(오프라인 FILE 재동기). 모뎀Pi는 받은 작업만 보관한다(§4.4).
- Python ESP노드 시뮬레이터.
- MQTT 브로커. 백홀은 WebSocket 하나로 한다.

## 2. 접근법 — B: 가짜 하드웨어로 3주 병행 → 부품 도착 즉시 수직 슬라이스

| 접근 | 요지 | 이유 |
|---|---|---|
| A. v2 §11 직렬 | 부품 오면 SF 실측부터 순서대로 | 첫 3주가 비고 웹 팀 대기. 기각 |
| **B. 가짜 하드웨어 병행** | fake 모뎀 + 호스트 렌더 프리뷰를 첫 3주 산출물로. 모뎀Pi 소프트웨어는 Pi 2대로 실기 통합. 부품 오면 수직 슬라이스 | 3주가 안 비고, 마일스톤마다 보여줄 게 생기며, 추가 산출물이 v2 §10.1이 요구한 테스트 인프라. **채택** |
| C. 노드 시뮬레이터까지 | B + Python 노드 시뮬레이터 | 상태 판단을 두 벌 유지(원칙 4 위반 위험). 기각 |

## 3. 3계층 토폴로지와 책임 분할

```
                    인터넷 (WebSocket, 모뎀Pi가 접속)                    LoRa 922.5 MHz
메인Pi ──────────┬──────────────▶ 모뎀Pi (학교A · 공학관) ─────┬──▶ ESP노드 E301-1
 웹·DB 원본       │                 링크(wj) ─▶ 파이프라인(cw)    ├──▶ ESP노드 E301-2
 버전·outbox      ├──────────────▶ 모뎀Pi (학교A · 본관)         └──▶ ESP노드 E302-1
 WS 허브          └──────────────▶ 모뎀Pi (학교B · …)
```

| 장비 | 책임 | 갖는 것 | 갖지 않는 것 |
|---|---|---|---|
| **메인Pi** | 관리자·학생 웹, 회원, 시간표·예약·시험기간 CRUD, CSV 임포트, **버전 부여(NEW_VER)**, 작업 생성(outbox), 모뎀Pi 등록·인증·노드 배정, 노드 상태 집계, 대시보드 | DB 원본, `room_versions`, `outbox`, `terminal_status`, `pending_devices`, 모뎀Pi 레지스트리 | 무선 파라미터 실행, TXN, 재시도, 프레임 바이트 |
| **모뎀Pi** | 메인Pi에 WS 접속(인증·재접속), 받은 작업 로컬 보관, **전처리**(유닛 분해·FILE 청킹·우선순위), **LoRa 워커**(TXN·재시도·FIFO·단일 인플라이트·CAD), 모뎀 펌웨어 제어, **매시 TIME(자기 NTP 시계)**, 업링크 전달 | 로컬 `jobs` 큐(SQLite), 노드 목록(메인이 내려줌), codec | 시간표 원본, 버전 부여, 사용자 |
| **ESP노드** | v2 §5~7 그대로 | — | — |

**버전은 메인Pi, TXN은 모뎀Pi.** NEW_VER는 "무엇이 최신인가"라 원본 옆에 있어야 하고, TXN은 "이 프레임을 재수신했는가"라 실제 송신·재시도가 일어나는 곳에 있어야 한다.

**NET_ID는 학교 단위**로 메인Pi가 배정한다(인접 캠퍼스 간섭 차단). 같은 학교의 건물끼리는 헤더의 BLD 바이트로 구분된다.

## 4. 영역 간 인터페이스 계약 (4주차 동결)

| 계약 | 양쪽 | 상태 | 위치 |
|---|---|---|---|
| ① 공중 프레임 규격 | 모뎀·노드 펌웨어 ↔ 모뎀Pi 파이프라인 | ◎ v2 §3 | `lora_proto/proto.h` + `proto.py` + `test_vectors.json` |
| ② 모뎀 시리얼 프로토콜 (JSON lines) | 모뎀 펌웨어 ↔ `modem.py` / fake 모뎀 | ◎ v2 §4.2·4.3 | S1 |
| ③ `lora_service/api.py` 시그니처 + `RecordProvider` | 메인Pi 웹 도메인 ↔ 메인Pi LoRa 계층 | ◎ v2 §8.6·8.7 (호출 측·구현 측 모두 wj, cw 리뷰) | S2 |
| ④ `RenderModel` | 노드 상태 판단(cw) → 렌더(dh) | ○ §4.1 | S3 |
| ⑤ CSV 포맷 + 웹 REST 윤곽 | 관리자·학생 웹 ↔ 메인Pi | ○ | S2 |
| **⑥ 메인Pi ↔ 모뎀Pi 백홀 (WebSocket)** | 메인Pi WS 허브(wj) ↔ 모뎀Pi 링크(wj) | ○ §4.2 | S2·S5 |
| **⑦ 모뎀Pi 내부 `JobStore`** | 링크(wj) ↔ LoRa 파이프라인(cw) | ○ §4.3 | S5·S6 |

### 4.1 `RenderModel` (확정)

상태 판단(cw)이 채워서 렌더(dh)에 넘기는 유일한 데이터. 렌더는 이 구조체 밖의 것을 읽지 않는다.

```c
typedef struct {
  uint8_t  layout;              // v2 §5.3 표의 1~8
  char     bld; uint16_t room; uint8_t unit;
  char     nowStr[6];           // "HH:MM" — 렌더가 시계를 직접 읽지 않음
  uint8_t  weekday;             // 1=월..7=일
  struct { char subj[21]; char prof[13];
           uint8_t sH,sM,eH,eM; uint8_t type; uint8_t flags; } prev, cur, next;
                                // flags bit0 = 존재함, bit1 = 변경 배지(휴강·보강·변경)
  uint8_t  nToday;
  struct { uint8_t sH,sM,eH,eM; char subj[21]; uint8_t type; } today[12];
  char     qrUrl[48];           // 학생웹 진입 URL. 비어 있으면 QR 생략
  uint16_t battMv; uint8_t battPct;
} RenderModel;                  // ≈ 600 B, 매 웨이크 재계산
```

- 문자열 길이는 v2 §5.1 저장 버퍼와 동일. `today[12]`는 09:00~21:00 가정(§10).
- QR URL은 메인Pi 주소이므로 펌웨어 상수가 아니라 **메인Pi → 모뎀Pi `config` → TIME 페이로드 확장 또는 별도 CMD**로 배포. 수단은 S8 spec.
- 픽스처: `firmware/test/fixtures/render/*.json`. Python 프리뷰와 C++ Unity 테스트가 같은 파일을 읽는다.

### 4.2 계약 ⑥ — 메인Pi ↔ 모뎀Pi 백홀 (WebSocket, JSON 메시지)

모뎀Pi가 `wss://<메인Pi>/ws/modem`에 접속한다. 메인Pi는 FastAPI WebSocket 엔드포인트. 메시지는 `{"t": "<type>", ...}` JSON 한 줄.

| 방향 | `t` | 필드 | 비고 |
|---|---|---|---|
| 모뎀Pi → 메인 | `hello` | `modem_id`(예 `"mjc-eng"`), `token`, `agent_ver`, `modem_fw`, `pending_results: int` | 토큰 불일치면 메인이 연결을 닫는다 |
| 메인 → 모뎀Pi | `config` | `net_id`, `radio: {sf, bw, cr, tx_dbm, preamble_wake_ms}`, `nodes: [{bld, room, unit}]`, `qr_base_url`, `status_hour_utc` | hello 직후 1회 + 변경 시 |
| 메인 → 모뎀Pi | `job` | `job_id`, `bld`, `room`, `unit`(0 = 호수 전체), `type`, `payload`(JSON, codec 입력), `priority`, `new_ver` | FILE은 `payload.records[]`에 **레코드 전체 포함** |
| 모뎀Pi → 메인 | `job_accepted` | `job_id` | 로컬 큐에 기록 완료. 메인은 이때 `dispatched` |
| 메인 → 모뎀Pi | `cancel` | `job_id` | 아직 `received` 상태면 취소 |
| 메인 → 모뎀Pi | `time_now` | `request_status: bool` | TIME 즉시 송출 |
| 모뎀Pi → 메인 | `job_result` | `job_id`, `state`(`acked`\|`failed`), `ack_status`, `ack_detail`, `attempts`, `txn`, `rssi`, `snr`, `sched_ver`, `resv_ver`, `exam_ver`, `ident_ver`, `batt_mv`, `layout`, `fw`, `last_error`, `finished_at` | 유닛 분해 시 유닛마다 1건 |
| 모뎀Pi → 메인 | `uplink` | `kind`(`STATUS`\|`HELLO`), `bld`, `room`, `unit`, `mac`, 나머지 v2 §3.3 STATUS/HELLO 필드, `rssi`, `snr` | HELLO는 `bld=0, room=0` |
| 양방향 | `ping` / `pong` | — | 30 s. 2회 무응답이면 끊고 재접속 |

**메시지 인코딩 규칙 (2026-09-14 확정, S2에서)**

| 대상 | 규칙 |
|---|---|
| `job.payload` 키 | `lora_proto.codec` dataclass 필드명과 동일. **단 `new_ver`는 제외** — job 최상위 `new_ver`가 진실원이다. 모뎀Pi는 codec 객체를 만들 때 `job.new_ver`를 주입한다 |
| `payload`의 bytes 필드 (`SET_ROOM.mac`, `CMD.args`) | **소문자 hex 문자열**, 구분자 없음 (`"a0b1c2d3e4f5"`). `lora_proto.jsonio.to_json/from_json`이 유일한 변환기 — 메인Pi·모뎀Pi 모두 그것만 쓴다 |
| `SET_ROOM.payload.bld` | **정수(ASCII 코드, 예 `69`)**. job 최상위 `bld`는 **문자 1자(`"E"`)** — 둘은 표현이 다르다 |
| `type="FILE"`의 `payload` | `{"kind": 1\|2\|3, "records": [레코드 dict…]}`. 각 레코드에 **`new_ver` 키 없음**(파일 본문 레코드는 NEW_VER 바이트가 없다 — v2 §3.3). 모뎀Pi는 `build_file(kind, records, job.new_ver)`로 조립 |
| `job_id` | **정수**. 계약 ⑦ `jobs.job_id`는 TEXT이므로 모뎀Pi가 문자열로 echo해도 메인은 `int()`로 받는다 |
| `uplink.mac` | 소문자 hex 12자, 구분자 없음. STATUS는 `mac` 없음(`null`) |
| `uplink`의 주소 | STATUS는 `bld`가 **문자 1자**, HELLO는 `bld=0, room=0, unit=0`(정수) |
| `uplink`의 ACK 필드 | codec `Ack` 필드명 그대로 평탄화(`status, detail, batt_mv, sched_ver, resv_ver, exam_ver, ident_ver, fw, layout`). STATUS는 `rssi_last, snr_last_x4, flags, uptime_h` 추가. `rssi`/`snr`은 **모뎀이 측정한 링크 값**으로 별도 필드 |

**작업 상태 (메인Pi `outbox.state`)**: `queued → dispatched → acked | failed | cancelled`. 규칙:
- 메인은 연결된 모뎀Pi에 `queued`만 보낸다. `dispatched`는 모뎀Pi 로컬 큐에 있으므로 재전송하지 않는다 → 중복 송신 없음.
- 모뎀Pi가 끊겼다 재접속하면 `hello.pending_results`로 미보고 결과 수를 알리고 곧바로 `job_result`를 몰아 보낸다.
- 모뎀Pi가 **24 h 이상** 끊겨 있으면 메인은 그 모뎀Pi의 `dispatched`를 `failed(last_error="modem_offline")`로 돌리고 대시보드에 노출한다.
- `GAP` 결과 → 메인이 `RecordProvider`로 레코드를 읽어 FILE `job` 생성(v2 §8.3 규칙 유지). 원본은 메인 하나.
- 프로비저닝: 미설정 노드 HELLO → `uplink` → 메인 `pending_devices(modem_id, mac)` → 관리자가 강의실 배정 → 그 모뎀Pi로 `SET_ROOM` job + `config.nodes` 갱신.
- 링크는 같은 `job_id`의 중복 삽입을 **무시**한다(멱등). 메인은 같은 연결에서 이미 보낸 `job_id`를 다시 보내지 않으며, 재접속하면 그 집합을 비우고 `queued`만 다시 보낸다.
- `job_accepted`가 이미 `cancelled`인 행에 오면 메인은 그 자리에서 `cancel`을 되돌려 보낸다(취소 경합).
- `GAP` 재동기는 **pending 작업이 있어도 억제하지 않는다**(GAP은 노드가 관측한 불연속). 단 FILE 작업의 결과가 GAP이어도 재동기를 다시 걸지 않는다 — FILE은 전체 교체라 v2 §3.3 보강대로 노드가 항상 OK를 낸다.

### 4.3 계약 ⑦ — 모뎀Pi 내부 `JobStore` (링크 ↔ 파이프라인)

모뎀Pi 안에서 wj의 링크와 cw의 파이프라인은 **같은 프로세스에서 SQLite 파일 하나**를 사이에 두고 만난다. 서로의 모듈을 import하지 않는다. 계약은 테이블 하나와 그 위의 얇은 Python 인터페이스다.

```sql
CREATE TABLE jobs (
  job_id      TEXT PRIMARY KEY,          -- 메인Pi가 준 id
  bld TEXT NOT NULL, room INTEGER NOT NULL, unit INTEGER NOT NULL,   -- unit 0 = 호수 전체 (파이프라인이 유닛별로 분해해 sub-row 생성)
  parent_id   TEXT,                      -- 유닛 분해된 행이면 원본 job_id
  type        TEXT NOT NULL,             -- 'SLOT_SET' … 'FILE' 'CMD' 'SET_ROOM' 'TIME'
  payload     TEXT NOT NULL,             -- JSON (codec 입력)
  priority    INTEGER NOT NULL DEFAULT 5,
  new_ver     INTEGER,
  state       TEXT NOT NULL DEFAULT 'received',   -- received|sending|acked|failed|cancelled
  attempts    INTEGER NOT NULL DEFAULT 0,
  next_try_at REAL,                      -- epoch
  txn INTEGER, ack_status INTEGER, ack_detail INTEGER, rssi INTEGER, snr REAL,
  node_vers   TEXT,                      -- JSON {sched,resv,exam,ident}
  batt_mv INTEGER, layout INTEGER, fw INTEGER, last_error TEXT,
  received_at REAL NOT NULL, finished_at REAL,
  uploaded    INTEGER NOT NULL DEFAULT 0 -- 링크가 job_result를 메인에 보냈으면 1
);
CREATE INDEX ix_jobs_pick   ON jobs(state, priority, next_try_at, received_at);
CREATE INDEX ix_jobs_upload ON jobs(uploaded, finished_at);
```

| 누가 | 하는 일 | 인터페이스 (`modempi/store.py`, 공용) |
|---|---|---|
| 링크(wj) | `job` 수신 → `received` 행 삽입 후 `job_accepted` 송신. `cancel` → `received`면 `cancelled`. 주기적으로 `finished_at IS NOT NULL AND uploaded=0` 행을 `job_result`로 올리고 `uploaded=1`. `config` 수신 → `config` 테이블 갱신 + 파이프라인에 이벤트 | `put_job(...)`, `cancel_job(id)`, `pending_results()`, `mark_uploaded(ids)`, `set_config(dict)` |
| 파이프라인(cw) | `received`를 v2 §8.4 순서(priority, received_at, 같은 노드에 `sending` 있으면 건너뜀)로 집어 `sending` → 전처리·송신·재시도 → `acked`/`failed` + 결과 필드 + `finished_at`. 유닛 분해는 sub-row 삽입(`parent_id`). TIME은 파이프라인이 스스로 `TIME` 행을 만든다(매시 `:00:05`, `config.status_hour_utc`에 REQUEST_STATUS) | `pick_next()`, `update(id, **fields)`, `add_subjobs(parent, [...])`, `get_config()`, `on_config_changed(cb)` |
| 링크(wj) | `uplink`: 파이프라인이 `uplinks` 테이블에 넣은 STATUS/HELLO 행을 올리고 `uploaded=1` | `put_uplink(dict)` / `pending_uplinks()` / `mark_uplinks_uploaded(ids)` |

이 분할의 효과: **wj는 fake 허브(pytest 안의 WS 서버)로, cw는 fake 모뎀 + `put_job()`으로** 각자 하드웨어·상대방 없이 테스트한다. 4주차 통합은 Pi 2대에 실제로 올려 `job → 로컬 큐 → fake 모뎀 → job_result`가 도는지 확인한다.

### 4.4 오프라인 동작 (모뎀Pi)

- 인터넷 단절 시: 로컬 큐의 `received`를 계속 송신하고, **TIME은 자기 NTP 시계(마지막 동기)로 매시 계속 송출**한다. 결과는 쌓아두고 재접속 시 보고.
- 시간표 사본은 갖지 않으므로 단절 중 새 변경·GAP 재동기는 불가 — ESP노드는 자기 시계·자기 데이터로 올바른 화면을 유지하므로(v2 원칙 3) 허용한다.
- NTP도 안 되는 장기 단절: 모뎀Pi RTC 없음 → 부팅 후 NTP 동기 전엔 TIME 송출 중지(`CLOCK_STALE`로 노드가 알린다).

### 4.5 v2 §8 개정 요약

| v2 §8 항목 | 어디로 |
|---|---|
| `codec.py`, `modem.py`, `worker.py`(§8.4 알고리즘), TIME 스케줄러, 업링크 1차 처리 | **모뎀Pi `modempi/lora/`** (cw) |
| `outbox`, `room_versions`, `terminal_status`, `pending_devices`, `lora_log`, `api.py`, `RecordProvider` | 메인Pi `server/lora_service/` (wj 구현, cw 리뷰). `outbox.state`에 `dispatched` 추가, `modem_id` 컬럼 추가 |
| 신규 | 메인Pi WS 허브 `server/lora_service/hub.py`(wj), 모뎀Pi 레지스트리 `modems` 테이블(`modem_id, school, building, token_hash, net_id, last_seen_at`) |
| §8.8 운영 | 메인Pi: FastAPI 프로세스 안에 허브. 모뎀Pi: `systemd` 서비스 1개(`modempi` 프로세스 안에 링크·파이프라인 asyncio 태스크) |
| `lora_log` | 프레임 로그가 아니라 **메인Pi↔모뎀Pi WS 메시지 로그**(`at, modem_id, dir, t, body`)로 재정의. 프레임 hex 로그는 모뎀Pi 쪽(S6)에 있다 (2026-09-14, S2) |

## 5. 서브프로젝트 분해

◎ = v2 스펙이 상세 정의, ○ = 새 spec 필요.

| # | 서브프로젝트 | 담당 | HW | 기존 스펙 | 의존 |
|---|---|---|---|---|---|
| S1 | `lora_proto` + C++/Python codec + 테스트 벡터 + **fake 모뎀** | cw | ✗ | ◎ §2·§3·§4 | — |
| S2 | **메인Pi 서버**: 도메인(학교·건물·강의실·시간표·예약·시험·사용자), CSV 임포트, REST, `lora_service`(outbox·버전·`api.py`·**WS 허브**·모뎀 레지스트리) | wj (cw: `lora_service` 리뷰) | ✗ | ◎ §8 개정 / ○ | S1(proto.py) |
| S3 | 렌더 계층 이식 + 호스트 PNG 프리뷰 | dh | ✗ | ○ | — |
| S4 | 관리자 웹: 시간표·휴강·예약·시험기간 CRUD, CSV 업로드, **모뎀Pi 등록·노드 배정**, 노드 상태 모니터 | wj + mh | ✗ | ○ | S2 |
| **S5** | **모뎀Pi 링크**: WS 클라이언트·인증·재접속·`JobStore` 삽입·결과/업링크 업로드·`config` 수신 | wj | Pi | ○ §4.2·4.3 | S2 허브 |
| **S6** | **모뎀Pi LoRa 파이프라인**: `JobStore` 소비 → 전처리(유닛 분해·FILE 청킹) → 워커(TXN·재시도·FIFO) → `modem.py` → TIME 스케줄러 → 업링크 파싱 | cw | Pi (+fake 모뎀) | ◎ §8.4 이관 / ○ §4.3 | S1 |
| S7 | 모뎀 펌웨어 + P0 SF 실측 | cw (dh 지원) | ✓ | ◎ §4·§10.3 | S1, HW |
| S8 | 노드 펌웨어 깨어있는 모드 + S3 결합 | cw + dh | ✓ | ◎ §5·§6 | S1, S3, S7 |
| S9 | 노드 절전(WOR)·프로비저닝·STATUS | cw | ✓ | ◎ §6.7·§7 | S8 |
| S10 | 학생 웹 + QR + 분석 대시보드 | wj + mh | ✗ | ○ | S2, S4 |
| S11 | Pi 2대 이식·2대 소크·케이스·전력 실측 | cw | ✓ | ◎ §10.4·10.5 | S9 |

```
S1 proto ──┬──▶ S2 메인Pi ──▶ S4 관리자웹 ──▶ S10 학생웹·대시보드
           │        │ (허브)
           │        └────▶ S5 모뎀Pi 링크 ──┐
           │                                ├─[JobStore]─▶ 4주차 Pi↔Pi 통합 (fake 모뎀)
           ├──▶ S6 모뎀Pi 파이프라인 ───────┘
           │                                 │
S3 렌더 ───┼──▶ S8 노드(awake) ◀── S7 모뎀펌웨어 ◀── [HW 도착 5주차]   ← 첫 E2E, 7~8주차
           │        │
           │        ▼
           │      S9 WOR·프로비저닝 ──▶ S11 Pi 이식·소크·전력
```

**부하.** cw: S1·S6·S7·S8·S9·S11. wj: S2·S4·S5·S10. 2~4주차엔 cw가 S1+S6, wj가 S2+S5로 각자 모뎀Pi의 절반을 갖고 4주차에 만난다. 5주차 이후 cw는 펌웨어에 집중하고 wj는 웹에 집중한다. dh는 S3 후 S7(모뎀 펌웨어는 RadioLib 스케치 수준)을 거들어 cw를 덜어준다.

## 6. 하드웨어 없는 3주(2~4주차)의 산출물

### 6.1 fake 모뎀 (`modempi/lora/fake_modem.py`, S1)
v2 §4.2·4.3의 JSON lines를 그대로 말하는 Python 객체. `modem.py`는 실물이든 fake든 같은 인터페이스. 시나리오 주입(`no_ack`, `GAP`, `BUSY`, `FILE_MISSING(seq)`, `cad_busy`, `DUP`), 가상 노드 버전 상태 보유, 프레임 hex 로그.

### 6.2 fake 허브 (`server/tests/fake_hub.py`, S2)
pytest 안에서 뜨는 최소 WS 서버. S5 링크가 `hello → config → job → job_accepted → job_result` 왕복을 상대방 없이 검증한다.

### 6.3 렌더 프리뷰 (`firmware/tools/render_preview.py` + `[env:native]`, S3)
GxEPD2와 같은 `drawPixel/print` 인터페이스의 호스트용 프레임버퍼 → 800×480 3색 → PNG. 픽스처 8개 레이아웃 × 경계 케이스 약 15개. 같은 native env가 `determineLayout`·`nextChangeAt` Unity 테스트를 실행.

### 6.4 주차별 산출물

| 주차 | cw | dh | wj | mh |
|---|---|---|---|---|
| 2 | S1 spec·plan, `proto.h`/`proto.py`, S6 spec | S3 spec, 프레임버퍼 클래스 | S2 spec(도메인·CSV·REST·⑥), S5 spec | 디자인 토큰·`components/ui` |
| 3 | codec 양방향 + 벡터 CI ✔, fake 모뎀, `JobStore` | v1 렌더 이식, 픽스처 8개, 첫 PNG | DB·마이그레이션, CSV 임포트, WS 허브, fake 허브 | 관리자 화면 마크업(mock) |
| 4 | S6 파이프라인 + fake 모뎀 테스트 ✔, **계약 7개 동결**, **Pi↔Pi 통합** | 레이아웃 8개 PNG 리뷰 완료 | S5 링크 ✔, `api.py`, **Pi↔Pi 통합** | 관리자 화면 ↔ 실제 API |
| 5~7 | P0 SF 실측 → S7 모뎀 펌웨어 → S8 노드 awake | 실제 패널 렌더, S7 지원, S8 저장·`nextChangeAt` | 관리자 웹 ↔ 실기 | 관리자 웹 완성 |
| **7~8** | **첫 E2E — 중간점검** (메인Pi → 모뎀Pi → 노드 1대) | | | |
| 8~10 | S9 WOR·프로비저닝 | 화면 폴리싱·QR | S10 학생웹 API·대시보드 집계 | S10 화면 |
| 11 | S11 Pi 이식, 2대 소크, 판넬·보고서 | | | |
| **12** | **경진대회** | | | |
| 13~15 | 전력 실측, 케이스, 최종발표 | | | |

## 7. 마일스톤별 완료 기준

| 시점 | 보여줄 것 | 완료 기준 (측정 가능) |
|---|---|---|
| 4주차 | Pi↔Pi 통합 | 계약 7개 문서화. S1 CI 녹색. 메인Pi 웹에서 저장 → 모뎀Pi fake 모뎀 로그에 프레임 hex → `job_result`가 메인 대시보드에 `acked`로. 렌더 PNG 8장 |
| 7~8주차 중간점검 | 웹 수정 → 메인Pi → 모뎀Pi → LoRa → e-Paper (awake, 노드 1대) | v2 벤치 §10.2-1·3. **갱신 지연 50회 중 48회 이상 30 s 이내** |
| 12주차 경진대회 | 노드 2대 배터리·절전, 관리자·학생 웹, 대시보드, 두 Pi 분리 배치 | §10.2-2 웨이크 수신률 ≥ 95 %. **100회 중 95회 이상 30 s, 전부 90 s 이내.** 2대 동시 독립 갱신. 4시간 무교체. 모뎀Pi 인터넷 끊고 30분 후 재접속 → 결과 보고 정상 |
| 15주차 최종발표 | 위 + 전력·소크 | v2 §1.4 딥슬립 ≤ 120 µA·일 ≤ 15 mAh 실측표. 1주 소크 `last_seen_at` 공백 없음 |

### 7.1 갱신 지연 기준 (확정: 정상 30 s / 재전송 포함 90 s)

지연 = 메인 저장→허브 송신(≤ 0.1 s) + 인터넷(≤ 1 s) + 모뎀Pi 큐 픽업(≤ 0.5 s) + 전송·프리앰블(awake 0.3 s, WOR 1~3 s) + **e-Paper 리프레시(15~20 s, §10)** ≈ 20~25 s. 정상 경로는 30 s 안. v2 §8.4 재시도(5·20·60 s) 한 번이면 넘으므로 상한 90 s를 둔다. 95 %는 §10.2-2 수신률 기준과 같은 숫자.

측정: 시작 = 관리자 웹 저장 응답(`outbox.created_at`), 끝 = **e-Paper 리프레시 완료 후 ACK**(S8에서 렌더→ACK 순서 고정) → `finished_at − created_at`. SLOT_SET·RESV_SET 각 50회, 노드 2대 교대, 같은 방·다른 층 절반씩. 히스토그램을 S10 대시보드에 노출.

계획서 5.2-1)·6.1 문구는 "30초 이내(정상 수신 시)"로 보정.

## 8. 리스크 · 완충

| 리스크 | 확률 | 대응 |
|---|---|---|
| 부품 지연(10월 중순 이후) | 중 | 5~6주차를 S2·S4·S10 완성에. 7주차까지 안 오면 **중간점검은 Pi↔Pi + fake 모뎀 + 렌더 PNG로 시연** — 모뎀Pi까지는 실기라 설득력 유지 |
| 전시장 두 Pi 사이 Wi-Fi 불안정 | 중 | **휴대폰 핫스팟 또는 직결 이더넷.** 오프라인 동작(§4.4)이 있어 끊겨도 진행 중 작업은 완료됨 |
| WS 재접속·중복 방지 버그 | 중 | `dispatched` 규칙(§4.2)과 `JobStore` 멱등 삽입. 4주차 통합에서 "끊고 붙이기" 시나리오를 완료 기준에 포함 |
| SF9로 건물 커버 안 됨 | 중 | SF10·11 상향. `config.radio`로 메인이 내려주므로 펌웨어 재빌드 없음 |
| WOR 수신률 미달 | 중 | `preamble_wake_ms` 상향(역시 `config`). 최악 시 경진대회는 LIGHT 슬립 |
| cw 병목(5~10주차) | 중 | S6를 4주차에 fake로 완료. dh가 S7 지원·S8 저장 계층 |
| e-Paper 리프레시 20 s 초과 | 낮음 | §7.1 근거 수정 |

## 9. 테스트 전략 (CI)

| 영역 | 테스트 | 도구 |
|---|---|---|
| `lora_proto` | Python 벡터 ↔ C++ 파싱 바이트 일치, 역방향 | pytest + Unity(native) |
| firmware | `determineLayout`·`nextChangeAt` 경계값, 렌더 픽스처 PNG 스냅샷 | Unity(native) |
| server | 허브: fake 링크로 `hello/config/job/job_accepted/job_result` 왕복, `dispatched` 규칙, 24 h 오프라인 실패 처리. 도메인: CSV 정합성, `api.py` 트랜잭션 원자성, 버전 롤오버 | pytest |
| modempi | 링크: fake 허브 왕복·재접속·미보고 결과 몰아 보내기. 파이프라인: fake 모뎀 6종 시나리오, 유닛 분해, FILE 청킹·FILE_MISSING 재송, TIME 스케줄, TXN 롤링 | pytest |
| web | `src/api/` 픽스처, 컴포넌트 | Vitest |
| 통합(CI 밖) | Pi↔Pi(4주차), 실기 벤치(§10.2)·전력(§10.4)·소크(§10.5) | — |

## 10. 열린 결정

- **하루 최대 교시**: `today[12]` 가정. S3 spec.
- **7.5" 3색 리프레시 시간**: 15~20 s 가정. v1 실측값이 있으면 §7.1 교체.
- **QR URL 배포 수단**: TIME 페이로드 확장 vs 별도 CMD — S8 spec.
- **CSV 컬럼 규격·REST 엔드포인트·WS 인증 토큰 발급 방식** — S2 spec.
- **모뎀Pi 인터넷 연결 수단**(교내 Wi-Fi 인증 vs 유선) — 설치 시점 확인. 전시는 핫스팟.
- **부품 발주 확정일** — 확정 즉시 §6.4의 5주차 기점 갱신.

## 11. 다음 단계

승인 후 **S1(`lora_proto` + codec + fake 모뎀)** spec을 쓴다. S2(wj)·S3(dh)·S5(wj)·S6(cw) spec은 S1과 병행해 2주차 안에 시작한다.
