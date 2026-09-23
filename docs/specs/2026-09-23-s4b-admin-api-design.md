# S4b — 관리자 대시보드·모니터 API (요약·노드·실패 작업·건물 단위 조회·서버 채번) — 설계 (spec)

- 생성일시: 2026-09-23
- 수정일시: 2026-09-23
- 상위 문서: `2026-09-09-roadmap-design.md` §3(메인Pi "노드 상태 집계, 대시보드")·§5 S4. 인증·스코프는 `2026-09-23-s4a-auth-design.md`(선행). 원자료는 `2026-09-14-s2-server-design.md` §2(`terminal_status`·`outbox`·`modems`·`pending_devices`). 건물 단위 조회·채번은 이슈 #36(mh).
- 담당: wj @leemonta9482. 영역 `server/`. `lora_service/api.py`·`hub.py` 불변 — 집계는 라우터 층에서 ORM 읽기 조인.

## 0. 배경 · 위치

S2는 관리자 화면이 쓸 **원자료**(`/api/lora/status`·`/outbox`·`/modems`·`/pending`)를 열어 두었지만, 화면이 "지금 무엇이 문제인가"를 한 번에 보려면 방마다·항목마다 호출하고 `bld/room` 숫자를 방 이름으로 스스로 매핑해야 한다. S4a로 관리자·학교 스코프가 생기면 그 위에 **요약과 조인된 목록**을 얹는 것이 이 spec이다.

디자인 스펙(mh)은 진행 중이라 **API만 만든다** — 화면이 어떤 배치를 택하든 쓸 수 있는 모양으로. 일부는 안 쓰일 수 있음을 감수한다(응답은 additive, 폐기는 나중에).

이슈 #36이 요구한 건물 단위 조회 3개와, 그 곁다리(예약·시험 id 채번)를 함께 다룬다.

## 1. 목표 · 비목표

### 목표
- **요약** 1회 호출: 경고 8종의 **카운트 + 미리보기 N건** + 총계.
- **노드 목록**: `terminal_status`에 방·건물을 조인하고 경고를 서버가 판정해 `warnings[]`로.
- **실패 작업 목록**: 최근 N일 `failed` outbox에 방·건물 조인.
- **건물 단위 조회**: 시간표·예약·시험기간·outbox를 건물 하나로 한 번에(#36).
- **예약·시험 id 서버 채번**: 클라이언트가 id를 안 보내면 서버가 비어 있는 최소 id를 배정(#36 곁다리).
- 전부 관리자 전용 + 학교 스코프(S4a §3.3).

### 비목표 (이번엔 안 함 / 후속)
- 갱신 지연 히스토그램·배정률·공강·No-show 등 **분석 집계** — S10.
- 학생용 API — S10.
- 실패 작업 **재큐잉**(04:00 일일 작업) — S10 spec의 일일 작업으로. 여기서는 노출만.
- 예약·시험 PK를 `(room_id, id)` 복합으로 바꾸는 것 — 전시 규모에 과함. 전역 id + 서버 채번으로 충분(§2.5).
- 임계값을 설정(.env)으로 빼는 것 — 코드 상수. 바꿀 일 생기면 그때.
- 화면 배치 — mh.

## 2. 데이터 · 계약

### 2.1 경고 정의 (서버가 판정, 코드 상수)

| 키 | 판정 | 원자료 |
|---|---|---|
| `modem_offline` | `modems.connected = false` | 허브 실시간 |
| `unseen` | 기대 노드(`rooms × units`)에 `terminal_status` 행이 없거나 `last_seen_at < now − 48 h` | STATUS 일 1회(S2 §8.4) — 24 h면 오탐 |
| `low_batt` | `terminal_status.low_batt` | 펌웨어 StatusFlag |
| `resync` | `terminal_status.sync_state = 'resync'` | S2 §2.4 |
| `clock_stale` | `terminal_status.clock_stale` | |
| `failed` | `outbox.state = 'failed'` and `finished_at ≥ now − 7 d` | 오래된 건 노이즈 |
| `pending_devices` | `pending_devices` 행 (그 학교 모뎀 소속) | |
| `pending_approval` | `users.status = 'pending_approval'` | S4a |

상수: `UNSEEN_HOURS = 48`, `FAILED_DAYS_DEFAULT = 7`, `PREVIEW_DEFAULT = 5`, `PREVIEW_MAX = 20`. 시각은 앱 관행 naive UTC.

노드 하나가 여러 경고를 가지면 `warnings`에 전부 들어가고 카운트에도 각각 센다(경고별 카운트 = "이 경고를 가진 노드 수").

### 2.2 `NodeOut` — 기대 노드 × 상태

기대 노드 = 그 학교 `rooms`의 `(bld, room, unit)`(unit = 1..`units`). `terminal_status` 를 **LEFT JOIN** — 한 번도 보고 안 한 노드도 목록에 나온다(`unseen`).

```
room_id, building_id, building(name), bld, room, unit,
modem_id, mac, fw, batt_mv, rssi, snr,
sched_ver, resv_ver, exam_ver, ident_ver, layout,
clock_stale, low_batt, uptime_h, last_seen_at, last_ack_at, last_status_at, sync_state,
warnings: list["unseen" | "low_batt" | "resync" | "clock_stale"]
```
`terminal_status` 가 없으면 상태 필드는 `null`, `clock_stale/low_batt=false`, `sync_state="unknown"`, `warnings=["unseen"]`.

### 2.3 `SummaryOut` (안 2 — 카운트 + 미리보기)

```json
{
  "as_of": "2026-09-23T05:02:11",
  "totals": {"buildings": 3, "rooms": 42, "nodes": 40, "modems": 3},
  "warnings": {
    "modem_offline":    {"count": 1, "items": [{"modem_id": "mjc-eng", "last_seen_at": "…", "buildings": ["공학관"]}]},
    "unseen":           {"count": 2, "items": [NodeOut, …]},
    "low_batt":         {"count": 3, "items": [NodeOut, …]},
    "resync":           {"count": 1, "items": [NodeOut]},
    "clock_stale":      {"count": 0, "items": []},
    "failed":           {"count": 4, "items": [FailedOut, …]},
    "pending_devices":  {"count": 2, "items": [PendingOut, …]},
    "pending_approval": {"count": 5, "items": [UserOut, …]}
  }
}
```
- `items` 는 최대 `preview`(기본 5, 최대 20)건. `count` 는 전체 수.
- `items` 정렬: 노드류는 `last_seen_at` 오래된 순(가장 위험한 것 먼저), `failed` 는 `finished_at` 최신순, `pending_*` 는 오래된 순(먼저 온 것 먼저).
- `totals.nodes` = 기대 노드 수(`Σ units`), 보고 여부 무관.

### 2.4 `FailedOut` = `OutboxOut` + `room_id`, `building`
outbox `(bld, room)` → rooms 조인. 방이 지워진 outbox 행(조인 실패)은 목록에서 빠진다(스코프를 판정할 수 없음).

### 2.5 예약·시험 id 채번 (#36 곁다리)

`reservations.id`·`exam_periods.id` 는 **전역 u16 PK 그대로** 둔다(프로토콜 `resvId/examId` 는 노드 안에서만 멱등키지만, DB 를 복합 PK 로 바꾸는 비용이 전시 규모에 맞지 않음).

- `ResvIn.id`·`ExamIn.id` 를 **선택**으로. 없으면 서버가 `1..65535` 중 **비어 있는 최소값** 배정. 있으면 지금처럼 그 id 로 upsert(호환·수정 경로).
- 응답 `Enqueued` 에 `id` 추가(additive): `{"outbox_ids": [...], "id": 17}`.
- 빈 id 없음(65535 전부 사용) → 409 `"예약 id 소진"`. 실제로는 S10 일일 작업(지난 예약 삭제)이 id 를 돌려준다.
- 채번은 도메인 세션 안 `SELECT id FROM reservations ORDER BY id` 한 번 스캔 — 65535 이하 정수라 ms.
- 화면 규칙(mh 에게): **채번하지 말고 서버가 돌려준 `id` 를 쓴다.** 수정은 그 id 로 다시 POST.

### 2.6 건물 단위 조회 (#36)

| 경로 | 응답 | 정렬 |
|---|---|---|
| `GET /api/buildings/{id}/slots` | `SlotWithRoom[]` = `SlotOut` + `room_id` | `room_id, day, s_h, s_m` |
| `GET /api/buildings/{id}/reservations` | `ResvWithRoom[]` = `ResvOut` + `room_id` | `room_id, date, s_h, s_m` |
| `GET /api/buildings/{id}/exams` | `ExamWithRoom[]` = `ExamOut` + `room_id` | `room_id, date_start` |
| `GET /api/buildings/{id}/outbox?state=&limit=200` | `FailedOut[]`(같은 모양 — outbox + room_id + building) | `id desc` |

쓰기는 지금처럼 `/rooms/{id}/...`.

## 3. 접근 제어 / 제약

- 전부 `require_admin` + 학교 스코프(S4a). 건물 단위 조회는 `scope.get_scoped(Building)`, 요약·노드·실패는 관리자 학교로 필터. 타 학교 건물 → 404.
- `lora_service/api.py`·`hub.py`·`Topology`·`RecordProvider` 불변. `terminal_status`·`outbox`·`modems`·`pending_devices` 는 **도메인 세션에서 ORM 읽기만**(라우터 층이 `app.lora_service.models` 를 import 하는 것은 S4a T8 과 같은 방향 — lora_service 가 domain 을 import 하지 않는 규칙은 지켜짐).
- 요약은 요청마다 계산(캐시 없음). 전시 규모(방 수십·outbox 수천)에서 SQLite ms 단위. 느려지면 그때 캐시.
- `preview` 상한 20, `days` 상한 90, `limit` 상한 500 — 초과는 422.

## 4. 인터페이스 계약

### 4.1 `/api/admin/*` (신규 라우터 `app/domain/admin_router.py`)

| 메서드·경로 | 쿼리 | 응답 |
|---|---|---|
| `GET /api/admin/summary` | `preview=5` (1..20) | `SummaryOut` (§2.3) |
| `GET /api/admin/nodes` | `building_id?`, `only? ∈ warn\|unseen\|low_batt\|resync\|clock_stale` | `NodeOut[]` (§2.2). `warn` = 경고 1개 이상. 정렬 `building, room, unit` |
| `GET /api/admin/outbox/failed` | `days=7` (1..90), `limit=100` (1..500) | `FailedOut[]` `finished_at desc` |

### 4.2 기존 라우터 변경 (`app/domain/router.py`, additive)

- §2.6 건물 단위 조회 4개 추가.
- `POST /rooms/{id}/reservations`·`POST /rooms/{id}/exams`: `id` 선택, 응답 `Enqueued.id` 추가(§2.5).

### 4.3 스키마 (`app/schemas.py`, additive)
`SlotWithRoom`, `ResvWithRoom`, `ExamWithRoom`, `FailedOut`, `NodeOut`, `WarningBucket(count, items: list[Any])`, `SummaryTotals`, `SummaryOut`, `ModemBriefOut(modem_id, last_seen_at, buildings)`. `Enqueued.id: int | None = None`. `ResvIn.id: int | None`, `ExamIn.id: int | None`.

## 5. 영역별 영향

- `server/app/domain/admin.py` (신규): 쿼리 함수 `expected_nodes(s, school_id, building_id=None) -> list[NodeRow]`, `failed_outbox(s, school_id, days, limit)`, `summary(s, school_id, preview)`. 라우터가 얇게 감싼다.
- `server/app/domain/admin_router.py` (신규): §4.1.
- `server/app/domain/router.py`: §4.2. `server/app/schemas.py`: §4.3.
- `server/app/main.py`: 라우터 등록.
- `static/index.html`: 요약 JSON 을 `<pre>` 로 보여주는 블록 1개(개발 확인용).
- 로드맵 §4 계약 ⑤ "REST = OpenAPI" — 변화 없음(additive). 이슈 #36 은 이 spec 구현 PR 로 닫는다.
- modempi·firmware·lora_proto: 영향 없음.

## 6. 무회귀 · 롤아웃

- 마이그레이션 없음(스키마 변경 없음). 전부 additive.
- 기존 테스트 그대로. 추가 테스트:
  - 건물 단위 조회: 방 2개 슬롯·예약·시험이 `room_id` 와 정렬대로 / 타 학교 건물 404 / 건물 outbox `state` 필터
  - 채번: id 없이 POST → 1, 다시 → 2, 1 삭제 후 → 1(최소 빈 값), id 지정 upsert 는 기존대로, 응답 `id`. 시험기간도 동일. (65535 소진 409 는 monkeypatch 로 상한을 3 으로 낮춰 검사)
  - 노드 목록: `terminal_status` 없는 노드 `unseen`·`sync_state="unknown"` / 48 h 경계(clock 주입) / `low_batt`·`resync`·`clock_stale` 각각 / 복수 경고 / `only=warn`·`building_id` 필터 / 타 학교 노드 제외
  - 실패 목록: 7일 창 경계 / 방 삭제된 행 제외 / 타 학교 제외 / `days`·`limit` 상한 422
  - 요약: 8 버킷 `count` 와 `items` 길이(`preview`)·정렬 / `totals` / `preview=21` 422 / 학생 토큰 403 / 무인증 401
- 성능 스모크(테스트 아님, 수동): 방 100·outbox 5000 시드에서 `summary` < 100 ms.

## 7. 역할 분담

| 누가 | 무엇 |
|---|---|
| wj | 전부 |
| cw | 리뷰(라우터 층이 `lora_service.models` 를 읽기 조인하는 것 확인) |
| mh | 화면 스펙에서 이 응답 모양을 참고. 채번 규칙(§2.5) 반영 |

## 8. 성공 기준

- 관리자 토큰으로 `GET /api/admin/summary` 1회 → 8 버킷 카운트·미리보기·총계. 저배터리 노드 3개를 시드하면 `low_batt.count == 3`, `items` 에 건물명·호수 포함.
- 건물 하나 강의실 20개 시드 → `GET /api/buildings/{id}/slots` 1회로 전부, `room_id` 로 구분.
- `POST /rooms/{id}/reservations` 에 `id` 없이 두 번 → 1, 2.
- 타 학교 관리자에게는 위 전부 404 또는 빈 목록.

## 9. 열린 결정 (plan 단계에서 확정)

- `summary.warnings.modem_offline.items[].buildings` — 건물 이름 배열. 모뎀이 건물 미배정이면 빈 배열.
- `NodeOut.warnings` 순서 — 고정 `unseen, low_batt, resync, clock_stale`.
- `unseen` 판정에 `last_ack_at` 도 볼지 — 보지 않는다. STATUS 가 일 1회 오므로 `last_seen_at`(ACK·STATUS 둘 다 갱신) 하나로 충분.
- 채번 시 "최소 빈 값"을 쓰면 삭제된 예약의 id 가 곧바로 재사용된다 — 노드가 그 id 를 아직 갖고 있으면 `RESV_SET` 이 덮어쓰기(같은 id upsert)라 문제 없음(v2 §3 멱등키).
