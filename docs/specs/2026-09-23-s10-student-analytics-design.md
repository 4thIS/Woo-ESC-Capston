# S10 — 학생 API(빈 강의실·주간 시간표·예약 신청)·관리자 승인·04:00 일일 작업·분석 집계 — 설계 (spec)

- 생성일시: 2026-09-23
- 수정일시: 2026-09-23 (r2 — PR #38 cw 리뷰 반영: approve·cancel 은 같은 세션+커밋 뒤 알림, RecordProvider 에 approved·KST 창, 승격은 오늘+7 만, 재동기는 FILE kind·유닛별·방별 try, tzdata, 신청 철회=행 삭제·하루 10회, 벡터 JSON 픽스처) (r3 — 재검토: `reservations.pushed_at` 으로 승격·RESV_DEL 판단 — 놓친 날 따라잡기·id 재사용 안전·창 밖 이동 시 RESV_DEL, 승격 예약별 트랜잭션, 신청 검증·승인을 락 안으로, 일일 작업 실행 락)
- 상위 문서: `2026-09-09-roadmap-design.md` §1("점유율 = 시간표·예약 기반 배정률"), §5 S10, §7.1(갱신 지연 기준 30 s / 90 s). 상태 판단 규칙은 `2026-09-09-lora-v2-wor-design.md` §5.3(`determineLayout`)·§5.4(`nextChangeAt`)·§12(예약 창 7일). 선행 spec: S4a(`2026-09-23-s4a-auth-design.md` 역할·스코프), S4b(`2026-09-23-s4b-admin-api-design.md` 채번·요약 버킷).
- 담당: wj @leemonta9482. 영역 `server/`. `lora_service/api.py`·`hub.py` 불변(기존 `enqueue_resv_set/resv_del/full_sync` 만 호출).

## 0. 배경 · 위치

학생 웹은 **예약을 위한 최소 화면**(지금 빈 강의실 · 방 주간 표 · 내 신청)이고, 예약은 **항상 신청 → 관리자 승인**이다(2026-09-23 확정). 노드에는 예약을 오늘~7일치만 보내므로(v2 §12) 8일 이후 예약을 창 안으로 **승격**하고, 실패 전송을 흡수하고, 오래된 행을 치우는 **04:00 일일 작업**이 필요하다. 분석 집계는 관리자 전용이며 센서 없이 "배정률"과 노드 이벤트 로그(outbox)로 정의한다.

"지금 빈 강의실" 판정은 서버가 DB 로 직접 계산한다(`room_state`, 접근법 A) — 노드 펌웨어 `determineLayout` 과 **같은 규칙**을 서버에 두고 테스트 벡터로 묶는다. 노드가 보고하는 `terminal_status.layout` 은 하루 1회라 "지금"이 아니다.

## 1. 목표 · 비목표

### 목표
- 학생: 자기 학교 `reservable` 방의 **지금 빈 강의실**, 방 **주간 표**, **예약 신청·취소·체크인**, 내 신청 목록.
- 관리자: 신청 목록·승인·거절·취소. 승인 시 노드 전송.
- 04:00 일일 작업: 만료·승격·실패 재동기·정리·기록. 수동 실행 API.
- 분석(관리자): 배정률·공강·예약 통계(No-show 포함)·갱신 지연 히스토그램 + 원자료 표. 차트가 바로 그릴 수 있는 배열.
- 시각 규칙을 학교 시간대(KST)로 통일. S2 의 `put_resv` UTC 날짜 판정을 고친다.

### 비목표 (이번엔 안 함 / 후속)
- 학생 웹의 분석 화면 — 학생은 예약 최소 화면만.
- `terminal_status` 이력(가용성 추이)·배터리 추이 — 이력 테이블 없음. 소크 데이터는 wj-16 CSV 내보내기.
- 학생별 통계, 학교 간 비교(개인정보·범위 밖).
- 예약 알림 메일(승인·거절) — 후속. S4a 메일러가 있으니 붙이기 쉬움.
- 학교별 운영 시간·제약 설정 — 코드 상수. 필요해지면 `schools` 컬럼으로.
- 집계 캐시·스냅샷 테이블 — 요청마다 계산. 느려지면 그때.

## 2. 데이터 · 계약

### 2.1 스키마 (마이그레이션 `web_student`, additive)

```
reservations
  + status        TEXT NOT NULL DEFAULT 'approved'  -- requested | approved | rejected | cancelled | expired
  + requested_by  TEXT NULL FK users(email)         -- 학생 신청. 관리자 생성은 NULL
  + requested_at  DATETIME NULL
  + decided_at    DATETIME NULL
  + decided_by    TEXT NULL                          -- 관리자 email
  + reject_reason TEXT NULL
  + checked_in_at DATETIME NULL                      -- 자가 체크인
  + cancelled_at  DATETIME NULL
  + pushed_at     DATETIME NULL                      -- 마지막 RESV_SET enqueue 시각. NULL = 노드에 없음 (r3)
  INDEX ix_resv_room_date (room_id, date), INDEX ix_resv_requester (requested_by, status)

job_runs
  id INTEGER PK, name TEXT NOT NULL, ran_at DATETIME NOT NULL, result TEXT NOT NULL (JSON)
  INDEX (name, ran_at)
```

- 기존 행·관리자 CRUD(`POST /rooms/{id}/reservations`) → `approved`. **노드 전송·`room_state`·배정률에 들어가는 예약은 `approved` 뿐.**
- 학생 신청은 `type=6`(대여) 고정, `professor=""`, `subject` = 용도 한 줄(≤ `P.SUBJ_MAX` B).
- 전이: `requested → approved | rejected | expired`, `approved → cancelled`. 학생이 결정 전 신청을 거두면(철회) **행을 삭제**한다 — u16 id 를 바로 돌려줘 신청·철회 반복으로 id 가 소진되지 않게(리뷰 🟡). 종료 상태(`rejected|cancelled|expired`)는 불변.
- **No-show**(파생, 컬럼 없음) = `status='approved'` · `requested_by IS NOT NULL` · 종료 시각 지남 · `checked_in_at IS NULL`.

### 2.2 시각 규칙

- DB 는 naive UTC(앱 관행). **"지금"·요일·"오늘"·운영 시간은 `SCHOOL_TZ = Asia/Seoul`** 로 변환해 판정(노드 `TZ=KST-9` 와 동일). 의존성 `tzdata` — Windows 엔 시스템 tz DB 가 없어 `ZoneInfo` 가 실패한다(리뷰 🔴10). `app/domain/clock.py`: `now_utc()`, `to_local(dt)`, `local_today()`, `local_day_bounds(date) -> (utc_start, utc_end)`.
- `put_resv` 의 "오늘~7일" 창 판정(S2)을 UTC 날짜에서 **KST 날짜**로 고친다(자정~09시 사이 하루 어긋나던 것).
- 일일 작업 시각 `DAILY_HOUR_LOCAL = 4`(KST 04:00 = UTC 19:00 전날). STATUS(03:00 KST) 뒤.

### 2.3 `room_state(room_id, at) -> (layout, until)` — v2 §5.3·§5.4 서버판

입력: 방의 정규 `slots`, 그 날짜의 `approved` 예약, `exam_periods`, 지역 시각 `at`. 우선순위 **예약 > 시험기간 > 기본 시간표** (v2 §5.3 그대로).

1. 예약: `at.date` 의 승인 예약 중 `[start, end)` 에 `at` 이 들어가면 `typeToLayout(type)`.
2. 시험기간: `at.date` 가 어떤 `exam_periods` 안이고 `at` 이 그 요일 어떤 슬롯 안이면 **5**(시험중).
3. 기본: 그 요일 슬롯 안이면 — `type=1`(수업)은 분<50 → **1**(수업중) / 분≥50 → **2**(쉬는시간); 그 밖의 type 은 `typeToLayout(type)`. 슬롯 밖 → **4**(빈강의실).

`typeToLayout`: 1→1, 2→5, 3→3, 4→4, 5→6, 6→7 (v2 §5.3 표). **"비어 있음" = layout 4.**
`until` = 다음 상태 변화 시각(`nextChangeAt`): 현재 구간의 끝, 또는 다음 슬롯/예약 시작, 또는 자정. 없으면 자정.

테스트 벡터는 **JSON 픽스처** `tests/fixtures/room_state_vectors.json` — 펌웨어(S8)도 같은 파일을 읽어 대조한다. 단위는 자정부터의 분, **50분 규칙의 "분"은 시각의 분(minute-of-hour)**. 비수업 슬롯(휴강·특강·대여)에 `typeToLayout` 을 쓰는 규칙은 PR #38 에서 cw 가 노드도 따르기로 합의 — 해당 벡터는 `tentative` 표시. 야간 교시(#14)는 확정 전까지 xfail.

**`RecordProvider` 도 같은 규칙으로 맞춘다(계약 ③ 구현 변경, cw 리뷰):** 예약 레코드는 `status == 'approved'` 만, 7일 창의 "오늘"은 `clock.local_today()`. 안 고치면 GAP·STATUS 재동기·관리자 sync·일일 재동기의 FILE 에 신청·취소 예약이 실려 "대여중"으로 뜨고, 04:00 KST(=UTC 전날) FILE 이 막 보낸 오늘+7 RESV_SET 을 노드에서 지운다(리뷰 🔴6).

### 2.4 학생 신청 제약 (`app/domain/reserve.py`, 코드 상수)

| 규칙 | 값 | 위반 |
|---|---|---|
| 날짜 | KST 오늘 ~ 오늘+`RESV_HORIZON_DAYS`(7) | 400 |
| 시각 | 시작·끝 5분 단위, 시작 < 끝 | 422 |
| 길이 | `15 분 ≤ 길이 ≤ 120 분` | 400 |
| 과거 | 시작 시각 ≤ 지금 | 400 |
| 건수 | 학생당 `requested` + 미래 `approved` ≤ **3** | 400 |
| 방 | `reservable=1`, 자기 학교 | 404 |
| 겹침 | 같은 방 그 요일 정규 슬롯(type 무관) · `approved`/`requested` 예약 · 시험기간(해당 날짜 슬롯) 과 1분이라도 겹침 | 409 |

| 빈도 | 학생당 하루 신청 **10회** | 429 |
| 방 용량 | 방의 창(오늘~+7) 안 approved+requested **24 개**(노드 저장 한도) | 409 |

겹침 검사에 `requested` 도 포함 — 같은 시간에는 **선착순 1명만** 신청 가능. 검증~채번~커밋은 `_ID_LOCK` 안(관리자 승인의 재검사도 같은 락) — 동시에 들어온 두 신청이 둘 다 통과해 승인 때 서로 막히지 않게(r3). 관리자 승인 시 **겹침 재검사**(사이에 관리자가 직접 예약을 넣었을 수 있음), **이미 시작한 신청은 승인 409**.

### 2.5 04:00 일일 작업 (`app/domain/daily.py`)

| # | 작업 | 규칙 |
|---|---|---|
| 1 | 만료 | `requested` · 시작 시각 < 지금 → `expired` |
| 2 | 승격 | `approved` · **오늘 ≤ KST 날짜 ≤ 오늘+7** · **`pushed_at IS NULL`**(아직 노드로 안 보냄) → `push_set`(RESV_SET + `pushed_at`), **예약마다 자기 트랜잭션**·커밋 뒤 알림. 이미 보낸 예약은 다시 안 보낸다(배터리, 리뷰 🔴7). 서버가 꺼져 하루를 놓쳐도 다음 실행이 따라잡고, outbox 이력을 보지 않아 지운 예약의 id 재사용에도 속지 않는다(r3). 한 건이 실패하면 `pushed_at` NULL 로 남아 다음 날 재시도 |
| 3 | 실패 재동기 | 지난 24 h `failed` outbox(`last_error ≠ 'cancelled'`) 의 **`(bld, room, unit)`** 마다 실패한 kind 집합으로 `enqueue_full_sync(bld, room, kinds, unit=u)` 1회. FILE 은 `payload.kind` 로 kind 를 얻는다(`KIND_OF` 엔 FILE 이 없음 — 가장 필요한 CSV·GAP FILE 실패를 놓치던 것). `CMD`·`SET_ROOM`·`TIME` 제외. 방마다 try — 한 방의 NotFound 가 나머지를 멈추지 않음(리뷰 🔴8) |
| 4 | 정리 | `reservations.date < 오늘−90` 삭제 · 거절·만료 신청은 `date < 오늘−7` 삭제(id 반환) · `job_runs.ran_at < 오늘−90` 삭제 · `email_tokens.expires_at < 지금−7일` 삭제 |
| 5 | 기록 | `job_runs(name="daily", result={"expired": n, "promoted": n, "resynced": [[bld, room, unit, kinds], …], "pruned": {"reservations": n, "job_runs": n, "email_tokens": n}, "errors": [str, …]})` |

- 단계마다 자기 트랜잭션. 한 단계 실패는 로그 + `errors` 에 문자열 + 다음 단계 계속.
- 트리거: `main.py` lifespan 의 `daily_loop(interval_s=60)` — 매 tick KST 시각이 `DAILY_HOUR_LOCAL` 이상이고 **오늘 04:00(KST) 이후** `job_runs(name="daily")` 가 없으면 실행(그 전의 수동 실행은 세지 않는다). 서버가 04:00 에 꺼져 있었으면 다음 기동 첫 tick 에 실행.
- 수동: `POST /api/admin/jobs/daily`(관리자) → 즉시 실행, 같은 result. `GET /api/admin/jobs?name=daily&limit=30` 이력. 전 학교 대상 전역 작업이지만 멱등(보낸 예약은 다시 안 보냄)이라 어느 학교 관리자가 눌러도 안전. 자동·수동이 겹치지 않게 프로세스 락.
- `daily_loop` 는 **sleep 먼저**(기동 직후 바로 돌지 않음 — 테스트가 시계를 바꾸기 전에 실제 시각으로 도는 것 방지).

**노드 용량·공개 표시 (r4, 자체 점검).** 노드는 예약을 **24 개**까지 저장한다(v2 §5.1 `Resv resv[24]`, 넘으면 `STORE_FAIL`). 방의 창(오늘~+7) 안 approved+requested 가 24 면 학생 신청·승인·관리자 창 안 작성 409, `RecordProvider` 는 (date, 시작) 순 앞 24 개만, 승격은 그 방의 보낸 예약이 24 면 건너뛰고 `errors` 에 남긴다. 문 앞 e-Paper 는 누구나 보므로 **학생 예약의 과목은 노드에 `"학생 예약"`** 으로 보낸다(학생 API 가 남의 과목을 숨기는 규칙과 일치 — 신청자가 적은 목적은 본인·관리자 화면에만).

**`pushed_at` 규칙 (r3).** 예약이 노드에 가 있는지를 예약 행이 기억한다. 바꾸는 곳은 `reserve.push_set`(RESV_SET enqueue → 지금 시각)·`push_del`(보낸 적 있고 날짜가 안 지났으면 RESV_DEL → NULL) 둘뿐:

| 경로 | 동작 |
|---|---|
| 관리자 승인 | 창 안 → `push_set`. 창 밖 → NULL 로 두고 승격을 기다림 |
| 관리자 작성·수정(`POST /rooms/{id}/reservations`) | 새 날짜가 창 안 → `push_set`. 창 밖(옮김 포함) → `push_del`(옮기기 전 날짜 기준) |
| 관리자 삭제 | `push_del` 뒤 삭제. 없는 id·다른 방 id 는 200 `[]`(멱등) |
| 취소(학생·관리자) | `push_del` |
| 승격 | `pushed_at IS NULL` 인 창 안 승인 예약 → `push_set` |

RESV_SET 이 enqueue 뒤 노드에서 실패해도 `pushed_at` 은 남는다 — 방 버전은 올라갔으므로 03:00 STATUS 버전 비교 → FILE 재동기와 일일 실패 재동기(3단계)가 복구한다. 마이그레이션은 **KST 오늘~+7 의 기존 예약에 `pushed_at` 을 채운다**(S2 가 이미 보냈다 — NULL 이면 배포 직후 삭제에 RESV_DEL 이 안 나가고 첫 일일 작업이 한낮에 전부 다시 보낸다). 이미 끝난 예약(오늘이라도 종료 지남)은 승격·RESV_DEL 하지 않는다. 예약 쓰기(신청·철회·취소·승인·거절·작성·삭제·승격)는 전부 한 프로세스 락 안에서 읽고 커밋한다 — 동시 승인과 엇갈려 유령 예약이 남지 않게.

### 2.6 분석 정의 (`app/domain/analytics.py`)

| 지표 | 정의 |
|---|---|
| 배정률 | 방·날짜의 **운영 시간 `OPEN_HOUR=9`~`CLOSE_HOUR=21`(KST)** 중 배정된 분 / 720 분. `room_state` 의 **layout ∈ {1,2,3,5,6,7} 이면 배정, 4 면 빈**(쉬는시간 2 는 수업 사이라 배정으로 봄). 휴강(3)은 "배정됐으나 안 씀"이라 배정률에는 넣고 `unused_min` 으로 따로 센다 |
| 공강 | 방·요일의 빈 구간(layout 4) 목록 — 운영 시간 안에서 구간 병합 |
| 예약 통계 | 기간(`date` 기준) 내 `requested_at` 있는 예약의 상태별 수 + No-show(§2.1) + 체크인 수. **학생이 결정 전에 철회한 신청은 행이 지워져 집계에 없다**(`cancelled` 는 승인 뒤 취소만), 거절·만료는 7일 뒤 정리돼 그 이전 기간 수에서 빠진다(r3 명시). `no_show_rate = no_show / (approved 종료분)`, `checkin_rate = checked_in / (approved 종료분)` |
| 갱신 지연 | outbox `state='acked'` · `type ∈ {SLOT_SET, RESV_SET}` · `created_at ∈ 기간` → `seconds = finished_at − created_at`. bin 경계 `[0,10,20,30,45,60,90,120,∞)`, `p50/p95/max/n`, `within_30s`·`within_90s` 비율(로드맵 §7.1 기준) |

기간은 KST 날짜 `from~to`(양끝 포함), 기본 최근 30일, 최대 90일(정리 규칙과 동일). 시험기간·슬롯 계산은 `room_state` 를 하루 단위로 **구간 병합**해 분을 센다(분 단위 루프 아님).

## 3. 접근 제어 / 제약

| 경로 | 가드 | 스코프 |
|---|---|---|
| `/api/student/**` | `require_student` | 자기 학교 방·자기 신청. 타인/타교 404 |
| `/api/admin/reservations/**`, `/api/admin/jobs/**`, `/api/admin/analytics/**` | `require_admin` | 자기 학교 |
| 기존 `/api/rooms/{id}/reservations` | S4a 그대로(관리자) | |

- 주간 표의 **남의 예약**은 `{s_h, s_m, e_h, e_m, label: "예약됨"}` 만. 내 것·관리자 예약(`requested_by NULL`)은 `subject` 노출.
- 학생 API 의 outbox 생성은 **취소 시 `RESV_DEL`** 하나뿐. 승인(관리자)·승격(일일 작업)이 `RESV_SET`. `RESV_DEL` 은 **노드로 보낸 적 있는(`pushed_at`) 예약만** — 신청·창 밖 예약엔 없다(관리자 삭제도 같은 규칙, r3).
- approve·cancel 은 **요청 세션으로** `enqueue_*(…, session=s)` → 핸들러가 커밋한 뒤 허브 알림(S2c `_commit_notify`). 별도 세션으로 enqueue 하면 도메인 쓰기 락과 부딪혀 5 s 뒤 `database is locked`(리뷰 🔴5, cw 실측).
- `analytics/*` 는 요청마다 계산. 창 90일 상한(422). 방 ≤ 100·outbox ≤ 수천 에서 SQLite 수십 ms.
- 일일 작업은 단일 프로세스 전제(README `--workers 1`). `job_runs` 로 하루 1회를 보장(같은 날 두 번 안 돎; 수동 실행은 예외로 항상 돎).

## 4. 인터페이스 계약

### 4.1 학생 `/api/student/*`

| 메서드·경로 | 쿼리/본문 | 응답 |
|---|---|---|
| `GET /rooms/free` | `at?`(ISO 지역시각, 기본 지금), `building_id?` | `[FreeRoomOut{room_id, building_id, building, bld, room, layout: 4, free_until: "HH:MM" \| null}]` |
| `GET /rooms` | `building_id?` | `[RoomStateOut{room_id, building_id, building, bld, room, layout, until: "HH:MM" \| null}]` — `reservable=1` 만 |
| `GET /rooms/{id}/week` | `date?`(기본 오늘; 그 주 월~일) | `WeekOut{room: RoomStateOut, week_start: date, slots: SlotOut[], reservations: ResvPublicOut[], exams: ExamOut[]}`. `ResvPublicOut{id, date, s_h, s_m, e_h, e_m, mine: bool, label}` — `label` = 내 것/관리자 것이면 `subject`, 남의 것이면 `"예약됨"` |
| `GET /me/reservations` | `status?`(기본 `requested,approved`) | `ResvMineOut[]` = `ResvOut` + `status, requested_at, decided_at, reject_reason, checked_in_at, cancelled_at, room_id, building, room` |
| `POST /rooms/{id}/reservations` | `{date, s_h, s_m, e_h, e_m, subject}` | 201 `ResvMineOut` (`requested`, 서버 채번 — S4b `_free_id`·`_ID_LOCK`). 하루 10회 초과 429 |
| `POST /me/reservations/{id}/cancel` | — | `ResvMineOut`. `requested` → **철회(행 삭제, 응답 status `cancelled`)**; `approved` 는 시작 전만 → `cancelled` + (보낸 적 있으면) `RESV_DEL`. 시작 후 409 |
| `POST /me/reservations/{id}/checkin` | — | `ResvMineOut`. `approved` · 시작−10분 ≤ 지금 ≤ 시작+15분 · 미체크인. 창 밖 409 |

### 4.2 관리자 `/api/admin/reservations/*`, `/api/admin/jobs/*`

| 메서드·경로 | 동작 | 응답 |
|---|---|---|
| `GET /reservations?status=requested&building_id=&date_from=&date_to=` | 목록(기본 `requested`), 신청자 조인 | `ResvAdminOut[]` = `ResvMineOut` + `requester: {email, name, student_no} \| null` |
| `POST /reservations/{id}/approve` | `requested → approved` + 겹침 재검사(409) + 창 안이면 `enqueue_resv_set` | `ResvAdminOut` |
| `POST /reservations/{id}/reject` `{reason}` | `requested → rejected` | `ResvAdminOut` |
| `POST /reservations/{id}/cancel` | `approved → cancelled` + `RESV_DEL`(시작 후도 허용) | `ResvAdminOut` |
| `POST /jobs/daily` | 즉시 실행 | `JobRunOut{id, name, ran_at, result}` |
| `GET /jobs?name=daily&limit=30` | 이력 | `JobRunOut[]` |

S4b 요약 `warnings` 에 **`pending_reservations`** 버킷 추가(additive): `count` = `requested` 수, `items` = `ResvAdminOut` 오래된 순. (S4b spec §2.3 에 9번째로 반영.)

### 4.3 관리자 `/api/admin/analytics/*` (공통 `from`, `to` KST 날짜, 기본 최근 30일, 최대 90일)

| 경로 | 응답 |
|---|---|
| `GET /allocation?from&to&building_id&group=room\|building\|weekday` | `[{key, label, assigned_min, unused_min, total_min, rate}]` `rate desc` |
| `GET /free-slots?date&building_id` | `[{room_id, room, building, free: [{from: "HH:MM", to: "HH:MM"}]}]` |
| `GET /reservations?from&to&group=day\|week` | `{series: [{date, requested, approved, rejected, cancelled, expired, no_show, checked_in}], totals: {…같은 키…}, no_show_rate, checkin_rate}` |
| `GET /latency?from&to&type=SLOT_SET\|RESV_SET\|all` | `{n, bins: [{ge, lt, count}], p50, p95, max, within_30s, within_90s}` |
| `GET /latency/samples?from&to&type&limit=100` | `[{outbox_id, bld, room, unit, type, created_at, finished_at, seconds}]` `created_at desc` |

### 4.4 기존 변경
- `put_resv`(S2): 창 판정 KST(§2.2). 응답·동작 그대로.
- `RoomOut` 에 `reservable`(S4a) 이미 있음. 학생 API 는 그것만 노출.

## 5. 영역별 영향

- 신규: `app/domain/clock.py`, `app/domain/room_state.py`, `app/domain/reserve.py`(제약 검증·전이), `app/domain/daily.py`, `app/domain/analytics.py`, `app/domain/student_router.py`, `app/domain/admin_resv_router.py`(예약·jobs·analytics), `alembic/versions/web_student_<rev>.py`.
- 수정: `app/domain/models.py`(Reservation 컬럼, JobRun), `app/schemas.py`, `app/domain/router.py`(`put_resv` KST), `app/domain/admin.py`(요약 버킷 추가), `app/main.py`(라우터·`daily_loop`).
- `lora_service/api.py`·`hub.py`·`modempi`·`firmware`·`lora_proto`: 불변. `enqueue_resv_set/resv_del/full_sync` 호출만.
- 로드맵 §7.1 측정(50회 표)은 `latency/samples` 로 제공 — wj-11 중간점검 산출물.
- mh: 학생 웹 화면 스펙(mh-08)은 §4.1 응답을 전제로.

## 6. 무회귀 · 롤아웃

- 마이그레이션 additive(컬럼 8 + 테이블 1). 기존 예약 `approved`.
- 기존 테스트 그대로(`put_resv` KST 변경은 날짜를 오늘+1 로 계산하는 테스트라 무관).
- 테스트:
  - `room_state` 벡터 8개 + `until` / KST 변환(UTC 자정 전후) / `put_resv` 창 KST
  - 제약 7개 각각 / 선착순(두 학생 같은 시간) / 체크인 창 경계 / 취소 전이·`RESV_DEL` / 타교·타인 404
  - 관리자 승인(창 안 `RESV_SET`·창 밖 없음)·겹침 재검사 409·거절·취소 / 요약 `pending_reservations`
  - 일일 작업 5단계 각각(만료·승격·재동기 kind 집합·정리 id 반환·기록) / 하루 1회·수동 실행 / 한 단계 실패해도 계속
  - 승격(r3): 놓친 날(+3 인데 안 보냄) 따라잡기 / 이미 보낸 예약 안 보냄 / 지운 예약과 같은 id 의 옛 acked 이력에 속지 않음 / 한 예약 실패해도 나머지 전송·실패분 재시도 / 두 번 돌려도 0
  - `pushed_at`: 창 밖으로 옮기면 RESV_DEL / 안 보낸 예약 삭제·취소엔 RESV_DEL 없음 / 없는 id 삭제 200
  - 동시성: 같은 시간 두 학생 동시 신청 → 201 하나·409 하나
  - 분석: 배정률(구간 병합, 휴강 `unused_min`) / 공강 병합 / 예약 통계·No-show / 지연 bin·p50/p95·within / 90일 초과 422 / 학생 403
- 성능 스모크(수동): 방 100·outbox 5000·예약 2000 에서 `analytics/allocation` 30일 < 1 s. `allocation` 은 방·날짜마다 쿼리 3개(≈ 9000)라 200 ms 는 어렵다(리뷰 ⚪) — 넘으면 방별 기간 일괄 로드로(plan T8 `ponytail:` 주석).

## 7. 역할 분담

| 누가 | 무엇 |
|---|---|
| wj | 전부 |
| cw | 리뷰 — `room_state` 가 v2 §5.3 과 일치하는지, 일일 작업의 `enqueue_full_sync` 사용 |
| dh | `determineLayout` 확정 시 §2.3 벡터 대조(열린 결정) |
| mh | 학생 화면 스펙(mh-08)에 §4.1 반영 |

## 8. 성공 기준

- 학생 토큰: 09:30 에 `GET /api/student/rooms/free` → 수업 중인 방 제외, `free_until` 이 다음 슬롯 시작. 신청 → 관리자 승인 → outbox `RESV_SET` 1세트 → 학생 `checkin` 성공.
- 8일 뒤 예약 승인 → outbox 없음 → 날짜를 7일 앞으로 당긴 `daily` 수동 실행 → `promoted 1`.
- `analytics/latency` 가 fake 허브로 만든 acked 50건에서 `within_30s` 를 돌려준다.
- 기존 서버 테스트 전부 통과.

## 9. 열린 결정 (plan 단계에서 확정)

- `room_state` 3번 규칙에서 `type≠1` 슬롯(휴강·특강·대여) 처리를 `typeToLayout` 으로 둔 것 — v2 §5.3 문장은 수업만 언급. dh `determineLayout` 확정 뒤 벡터 대조로 맞춘다.
- 쉬는시간(layout 2)을 배정으로 센 것 — "수업 사이 10분"이라 방이 비어 있지 않음. 반대면 상수 하나.
- 운영 시간 09~21 — 야간 교시(#14 cw)가 확정되면 `CLOSE_HOUR` 조정.
- 승인·거절 메일 알림 — 후속. S4a `mailer.send` 재사용.
- `daily_loop` 의 tick 60 s — 04:00~04:01 사이 실행. 정확한 초는 의미 없음.
