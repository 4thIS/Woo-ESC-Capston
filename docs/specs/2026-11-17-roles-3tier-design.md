# 관리자 권한 3단계 — 최고 관리자 · 건물 관리자 · 일반 계정 (#160)

- 상태: 확정 (2026-11-17, 팀장 결정 #160 · wj 설계)
- 담당: wj (`server/`·`web/`)
- 관련: S4a 인증 스펙(`2026-09-23-s4a-auth-design.md`), `server/app/auth/scope.py`, `docs/design/screens/admin-users.md`

## 1. 목표

학교 규모가 커져도 관리자 한 명이 모든 건물을 맡지 않게, **건물 단위로 관리 권한을 나눠 준다.**

| 등급 | `users.role` | 만드는 방법 | 범위 |
|---|---|---|---|
| 최고 관리자 | `admin`(지금 그대로) | CLI `create-admin` 만 | 학교 전체 |
| 건물 관리자 | `building_admin`(새로) | 최고 관리자가 웹 회원 화면에서 지정 | `user_buildings` 에 적힌 건물들 |
| 일반 계정 | `student`(지금 그대로) | 웹메일 가입 | — (`/admin` 접근 불가) |

범위 밖: 노드 펌웨어 · LoRa(`lora_proto/`·`modempi/`) 는 바뀌지 않는다.

## 2. 데이터

### 2.1 `users.role`
CHECK 를 `('student', 'admin', 'building_admin')` 로 넓힌다. 기존 행은 그대로 — `admin` 은 최고 관리자, `student` 는 일반 계정이 된다.

### 2.2 `user_buildings` (N:M)
| 컬럼 | |
|---|---|
| `email` | FK `users.email` ON DELETE CASCADE |
| `building_id` | FK `buildings.id` ON DELETE CASCADE |
| PK | (`email`, `building_id`) |

- 범위 단위는 **건물**이다(모뎀Pi 아님). 모뎀Pi 는 건물을 따라간다 — 한 모뎀Pi 가 여러 건물을 맡아도 사용자가 볼 수 있는 것은 자기 건물의 강의실·노드·작업뿐이다.
- 건물을 지우면 그 행이 함께 지워진다. 건물이 0개가 된 건물 관리자는 관리자 화면에서 빈 목록만 본다(권한이 넓어지지 않는다).

### 2.3 `role_changes` (기록)
| 컬럼 | |
|---|---|
| `id` | PK |
| `email` | 바뀐 사람 |
| `changed_by` | 바꾼 최고 관리자 |
| `changed_at` | UTC |
| `from_role` · `to_role` | |
| `building_ids` | 바뀐 뒤 건물 id 목록(JSON 문자열) |

지우지 않는다(감사용). 학생 탈퇴 정리 등 다른 작업이 이 표를 건드리지 않는다.

### 2.4 학번 선택
가입(`POST /api/auth/verify`)의 `student_no` 를 **선택**으로 바꾼다. 비우면 `NULL`. 적으면 지금처럼 학교 안 중복을 막는다(부분 유일 인덱스는 NULL 을 세지 않는다 — 교직원 여럿이 학번 없이 가입할 수 있다).

## 3. 범위 규칙 (서버)

### 3.1 가드
| 가드 | 통과 | 쓰는 곳 |
|---|---|---|
| `SuperUser` | `admin` | 최고 관리자 전용 API |
| `ManagerUser` | `admin` · `building_admin` | 건물 단위로 나눌 수 있는 관리 API |
| `StudentUser` | `student` | 지금 그대로 |

**fail-closed**: 기존 `AdminUser` 는 `SuperUser` 와 같은 뜻으로 남긴다. 범위 검사를 붙인 API 만 `ManagerUser` 로 옮긴다 — 빠뜨린 API 는 건물 관리자에게 403 이지 남의 건물이 열리지 않는다.

### 3.2 `Scope`
`scope.of(s, user) → Scope(school_id, buildings)` — `buildings` 는 최고 관리자면 `None`(학교 전체), 건물 관리자면 `user_buildings` 의 `frozenset`. 요청마다 DB 에서 읽는다(토큰에 굽지 않는다 — 지정이 바뀌면 다음 요청부터 바로 맞다).

- `get_scoped(s, model, id, sc)` — 학교가 다르거나 **건물이 범위 밖이면 404**(존재를 숨긴다). Building · Room · Modem(그 모뎀을 가리키는 건물 중 하나라도 범위 안) · School.
- `room_keys(s, sc)` · `modem_ids(s, sc)` · `building_ids(s, sc)` — 목록·outbox·노드 상태 필터.
- 집계 함수(`domain/admin.py`·`analytics.py`)는 지금의 `school_id` 인자 옆에 `buildings` 를 받아 `Building.id IN (...)` 를 더한다.

### 3.3 API 분류

**건물 관리자도 쓰는 것(`ManagerUser` + 건물 범위)**
- 조회: `GET /api/schools`(자기 학교, 읽기만) · `GET /api/buildings`(범위 안만) · `GET /api/buildings/{id}/{slots,reservations,exams,outbox}` · `GET /api/rooms`
- 강의실: `POST /api/rooms`(범위 안 건물에만) · `PATCH|DELETE /api/rooms/{id}`
- 시간표 · 시험기간 · 관리자 예약 · 재전송 · CMD: `/api/rooms/{id}/…` 전부
- CSV: `POST /api/import/slots` — 범위 밖 건물의 행은 `building: 'X' 없음` 행 오류(존재를 숨긴다)
- 모니터: `GET /api/admin/{nodes,outbox/failed,summary}` · `GET /api/lora/{modems,outbox,status,pending}` · `POST /api/lora/outbox/{id}/cancel`
- 대기 노드 배정: `POST /api/lora/pending/{mac}/provision` — 자기 건물 모뎀이 본 노드를 자기 건물 강의실로만
- 학생 예약: `GET /api/admin/reservations` · `POST …/{approve,reject,cancel}`
- 분석: `GET /api/admin/analytics/*`

**최고 관리자만(`SuperUser`) — 건물 관리자는 403**
- 학교 설정 `PATCH /api/schools/{id}`
- 건물 만들기 · 고치기(`bld` · 모뎀 배정) · 지우기 `POST|PATCH|DELETE /api/buildings…`
- 모뎀Pi 등록 · 토큰 재발급 `POST /api/lora/modems…` · 시각 방송 `POST /api/lora/time`(모든 모뎀에 간다)
- 회원 `GET /api/admin/users` · 승인 · 거절 · 정지 · 해제 · **역할 지정**
- 일일 작업 `POST /api/admin/jobs/daily` · `GET /api/admin/jobs`(학교 구분 없는 전역 작업)

**요약(`/api/admin/summary`) 차이**: 건물 관리자에게 `pending_approval`(가입 승인 대기)은 항상 빈 목록이다 — 그 사람의 일이 아니다. 나머지 경고 · 총계는 자기 건물만 센다.

### 3.4 역할 지정 API
`PUT /api/admin/users/{email}/role` — `SuperUser` 전용. 본문 `{"role": "building_admin" | "student", "building_ids": [..]}`.
- `admin` 으로는 지정할 수 없다(422) — 최고 관리자는 CLI 만. 계정 하나가 털려도 관리자를 늘리지 못하게.
- 대상이 `admin` 이면 400(`관리자 계정은 CLI 로`). 대상은 자기 학교의 `active` 계정만(다른 학교 404, 그 밖의 상태 409).
- `building_admin` 이면 건물 1개 이상, 모두 자기 학교 건물(아니면 404). `student` 로 돌리면 건물을 비운다.
- **역할이나 건물이 실제로 바뀌면** `token_version += 1`(기존 로그인 끊김) + `role_changes` 한 줄. 같은 값으로 다시 보내면 아무것도 바꾸지 않는다(멱등).
- 응답 `UserOut` 에 `building_ids` 를 더한다(additive). 회원 목록도 같은 필드를 준다.

## 4. 웹

- **로그인 · 세션**: `building_admin` 은 관리자 앱으로 들어간다(앱은 `role === 'student' ? 학생 : 관리자`). 로그인 탭 `관리자` 로 로그인한다.
- **사이드바**: 내 정보 칸 이름 아래 등급 `최고 관리자` / `건물 관리자`. 건물 관리자에게는 `회원` 메뉴를 두지 않는다.
- **최고 관리자 전용 버튼 숨김**(건물 관리자): 건물 추가 · 건물 수정 · 건물 삭제, 모뎀Pi 등록 · 토큰 재발급 · 시각 브로드캐스트, 대시보드의 가입 승인 대기.
- 목록 · 선택지는 서버가 이미 자기 건물만 준다 — 화면이 따로 거르지 않는다.
- **회원 화면(최고 관리자)**: 활성 계정 행에 `건물 관리자 지정` · 건물 관리자 행에 맡은 건물 이름과 `건물 바꾸기` · `해제`. 지정 Modal 은 학교 건물 체크 목록(1개 이상) + 확인 문장 `지정하면 그 사람은 다시 로그인해야 합니다`.
- **가입**: 학번 칸을 선택(`학번 (선택)`)으로. 비워도 가입된다.

## 5. 시험

- **라우트 전수표**: 앱의 `/api/*` 라우트를 모두 모아, 각 라우트가 `공개` · `학생` · `관리자(건물 범위)` · `최고 관리자` 중 하나로 분류돼 있는지 확인한다. 새 라우트를 분류 없이 더하면 테스트가 실패한다.
- **관리자(건물 범위) 라우트마다** 건물 관리자가 *다른 건물*의 리소스를 부르면 404(목록 API 는 남의 건물 행이 없음).
- **최고 관리자 라우트마다** 건물 관리자 403.
- 학생은 관리자 라우트 전부 403(지금 동작 유지).
- 역할 지정: 최고 관리자 전용 · `admin` 지정 불가 · `token_version` 증가 · `role_changes` 기록 · 멱등.
- 학생 예약 승인은 그 건물의 건물 관리자와 최고 관리자만.
- 마이그레이션: 기존 행 그대로, 새 표 생성, CHECK 확장.

## 6. 운영 · 배포

- 마이그레이션은 additive(새 표 2 · CHECK 확장)다. 메인Pi 자동 배포가 `alembic upgrade head` 를 돈다.
- 경진대회(11/19~20) 중에는 main 머지 금지(#160) — PR 은 올리되 머지는 대회 뒤 팀장이 한다.
