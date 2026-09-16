# S2b — 시간표 CSV 임포트 (계약 ⑤ CSV 포맷) — 설계 (spec)

- 생성일시: 2026-09-16
- 수정일시: 2026-09-16
- 상위 문서: `2026-09-09-roadmap-design.md` §1(학사 연동 = 관리자 CSV 업로드)·§3(메인Pi 책임 "CSV 임포트")·§4 계약 ⑤. 도메인·outbox는 `2026-09-14-s2-server-design.md`(S2). FILE 의미는 `2026-09-09-lora-v2-wor-design.md` §3.3.
- 담당: wj @leemonta9482. 영역 `server/`. `server/app/lora_service/api.py` 추가분은 cw 필수 리뷰.

## 0. 배경 · 위치

학사포털 직접 연동은 비목표(로드맵 §1). 학기 시간표는 관리자가 포털에서 내려받은 CSV를 올리는 것이 **유일한 입력 경로**다. S2는 슬롯 1개씩 넣는 `PUT /api/rooms/{id}/slots`만 만들었고 CSV는 후속으로 미뤘다(S2 §1 비목표). 이 spec이 그 후속이며, 진행도 wj-04의 남은 절반이다(마이그레이션 뼈대는 S2에서 끝남).

CSV 컬럼 규격은 로드맵 §4 계약 ⑤ "CSV 포맷 + 웹 REST 윤곽"의 CSV 절반이다. 관리자 웹(S4, mh 화면 스펙 → wj 구현)의 "CSV 업로드" 화면은 이 spec의 응답 형식을 그대로 표시한다.

## 1. 목표 · 비목표

### 목표
- CSV 파일 하나로 여러 강의실의 정규 시간표를 한 번에 넣는다. 전체 검증 후 적용(all-or-nothing).
- **출처 우선순위 포털 < 수동 < 긴급.** 포털 CSV를 다시 올려도 관리자가 웹에서 손으로 고친 슬롯·긴급 휴강은 살아남는다.
- 변경된 강의실마다 노드에 **FILE(schedule 전체 교체)** 1회로 전달한다. 슬롯마다 SLOT_SET을 쏘지 않는다.
- 미리보기(`dry_run`)로 적용 전에 결과 요약을 볼 수 있다.

### 비목표 (이번엔 안 함 / 후속)
- 예약·시험기간·휴강 CSV — 건수가 적어 관리자 폼(S4)으로. 휴강은 `PUT /slots`에 `source=3`으로 넣는다.
- 강의실 자동 생성 — 강의실은 노드 배정과 묶여 있어 관리자가 명시적으로 만든다. CSV에 없는 강의실은 오류.
- 화면 — `static/index.html`에 무스타일 업로드 폼 1개만. 진짜 화면은 mh 스펙 뒤 S4.
- 인증 — 기획 미확정(S2와 동일).
- 파일 업로드 이력·롤백 — 응답 요약을 관리자가 보는 것으로 충분.

## 2. 데이터 · 계약

### 2.1 CSV 규격 (계약 ⑤ CSV)

UTF-8(BOM 허용), 헤더 행 필수, 컬럼은 **이름으로** 매칭(순서 무관, 대소문자 무관, 앞뒤 공백 무시). 한 행 = 슬롯 하나. 빈 행은 건너뛴다. 구분자 `,`(`csv` 모듈 기본 dialect — 따옴표 안 쉼표 허용).

```
school,building,room,day,start,end,type,subject,professor
우송대,E,201,월,09:00,10:30,수업,캡스톤디자인,홍길동
우송대,E,201,2,13:00,14:50,5,특강 AI,김철수
```

| 컬럼 | 값 | 오류 조건 |
|---|---|---|
| `school` | `schools.name`과 정확히 일치 | 없는 학교 |
| `building` | `buildings.bld` **글자 1자**(헤더 BLD 바이트). 이름이 아니다 | 그 학교에 없는 bld |
| `room` | 정수 1~9999 = `rooms.room` | 그 건물에 없는 방, 범위 밖 |
| `day` | `월 화 수 목 금 토 일` 또는 `1~7`(1=월) | 그 외 |
| `start`, `end` | `HH:MM` (`H:MM`도 허용) | 형식 오류, `end <= start` |
| `type` | `수업 시험 휴강 빈강의실 특강 대여` 또는 `1~6` | 그 외 |
| `subject` | 문자열 | UTF-8 `SUBJ_MAX`(20) 바이트 초과 |
| `professor` | 문자열, 빈 값 허용 | UTF-8 `PROF_MAX`(12) 바이트 초과 |

추가 검증(파일 전체):
- 같은 방·같은 `(day, start)` 행이 둘 이상 → 오류(나중 행에 "row N 과 중복").
- 방마다 `포털 행 수 + 그 방에 남을 source≥2 슬롯 수` > 48 → 오류(노드 슬롯 상한, v2 §12). `(day,start)`가 겹치는 상위 출처 슬롯은 포털 행이 skip되므로 이중으로 세지 않는다.
- 필수 컬럼이 헤더에 없으면 행 검사 없이 즉시 오류(`row: 0`).

### 2.2 출처 (`slots.source`)

| 값 | 이름 | 누가 쓰나 |
|---|---|---|
| 1 | 포털 | CSV 임포트만 |
| 2 | 수동 | `PUT /api/rooms/{id}/slots` 기본값 |
| 3 | 긴급 | `PUT /api/rooms/{id}/slots` 본문 `source: 3` (휴강 등) |

규칙: **낮은 출처는 높은 출처를 덮지 못한다.**
- CSV: 같은 키 `(room_id, day, s_h, s_m)`에 `source≥2` 슬롯이 있으면 그 행은 `skipped`(적용 안 함, 오류 아님).
- `PUT`: 기존 슬롯 `source > body.source`면 **409** `"source k 슬롯은 source ≥ k 로만 수정"`. 같거나 높으면 덮고 `source`도 본문 값이 된다. 출처를 낮추려면(긴급 → 수동) 삭제 후 재등록.
- `DELETE`는 출처를 보지 않는다(명시적 삭제).

마이그레이션 `web_slot_source`: `slots.source INTEGER NOT NULL DEFAULT 2`. 기존 행은 2(수동) — 포털 재업로드가 기존 데이터를 지우지 않도록 보수적으로.

### 2.3 적용 규칙

파일에 **나온 강의실만** 대상. 방마다:
1. 기존 `source=1` 슬롯 중 파일에 같은 키가 없는 것 → 삭제(`deleted`).
2. 파일 행 중 키가 `source≥2` 슬롯과 겹침 → `skipped`(사유 `"row N: 수동/긴급 슬롯 있음 (source=k)"`).
3. 나머지 행 → 같은 키의 `source=1` 슬롯이 있으면 갱신(`updated`, 내용이 같아도 updated로 센다), 없으면 삽입(`added`).
4. 방의 변경(1·3에서 하나라도)이 있으면 FILE 대상 방에 넣는다. 변경 0인 방은 FILE도 안 보낸다.

파일에 나오지 않은 강의실의 포털 슬롯은 손대지 않는다(건물별로 따로 내려받은 CSV를 여러 번 올릴 수 있게).

### 2.4 노드 전달 — `enqueue_file_replace` (lora_service 추가, cw 리뷰)

```python
def enqueue_file_replace(bld: str, room: int, kind: str, unit: int = 0) -> list[int]:
    """콘텐츠 변경 FILE: kind 버전 +1, 현재 RecordProvider 레코드로 FILE 을 새로 만들어 유닛별 삽입.
    재동기 FILE(enqueue_full_sync, bump 없음·queued 재사용)과 달리 기존 queued FILE 을 재사용하지 않는다."""
```

왜 재동기 FILE을 쓰지 않나: `enqueue_full_sync`는 같은 방에 queued/dispatched FILE이 있으면 **그 행(옛 내용)을 돌려준다**. 임포트 직후 옛 시간표가 나가고 새 내용은 영영 안 간다. 콘텐츠 FILE은 버전을 올리고 항상 새 행을 만든다 — 앞의 stale FILE이 먼저 나가더라도 뒤의 새 FILE이 덮는다(FILE은 전체 교체, v2 §3.3 "버전 연속성 판정 대상 아님"). 방당 한 번 bump이므로 유닛 간 핑퐁(S2에서 재동기 FILE bump를 없앤 이유)은 생기지 않는다.

RecordProvider는 DB를 자기 세션으로 읽으므로 **도메인 커밋 뒤에** 불러야 한다(§3).

## 3. 접근 제어 / 제약

- 처리 순서: 파싱·검증(DB 읽기만) → `dry_run`이면 요약 반환 → 도메인 세션에 적용 → `s.commit()` → 방마다 `api.enqueue_file_replace(bld, room, "schedule")` → 응답. S2의 "enqueue 먼저" 규칙(WAL 쓰기 락)은 여기선 뒤집힌다 — FILE 내용이 커밋된 레코드에서 나오기 때문. 커밋이 끝난 뒤 enqueue하므로 락 경합은 없다.
- 커밋 뒤 enqueue가 실패하면 500. DB는 반영된 상태. 응답 본문에 `"DB 는 반영됨 — POST /api/rooms/{id}/sync 로 재전송"`을 적는다. 관리자가 복구할 수 있고, 다음 변경·GAP 재동기로도 흡수된다.
- 요청 본문 상한 1 MiB(학기 시간표 수천 행이면 충분). 초과 413.
- 파일 인코딩이 UTF-8이 아니면(엑셀 CP949 저장) 400 `"UTF-8 로 저장하세요"`. 자동 감지 안 함.

## 4. 인터페이스 계약

### `POST /api/import/slots?dry_run=false`

- 요청: 본문 = CSV 텍스트 그대로. `Content-Type: text/csv` (multipart 아님 — `python-multipart` 의존 없이 `fetch(url, {body: file})`로 올린다).
- 200:
  ```json
  {"rooms": 3, "added": 40, "updated": 5, "deleted": 2,
   "skipped": [{"row": 7, "reason": "수동 슬롯 있음 (source=2)"}],
   "outbox_ids": [12, 13, 14]}
  ```
  `dry_run=true`면 `outbox_ids: []`, DB 변경 없음. `rooms`는 변경이 하나라도 있는 방 수.
- 400: `{"errors": [{"row": 7, "error": "day: '월요일' 은 월~일 또는 1~7"}, …]}` (전체 행 검사, 최대 100개까지 모아 보고). `row`는 헤더를 1로 센 파일 행 번호.
- 413 / 500: §3.

### `PUT /api/rooms/{id}/slots` 변경 (additive)

`SlotIn.source: int = Field(2, ge=1, le=3)`. `SlotOut`에 `source` 노출. 409는 §2.2.

### `GET /api/rooms/{id}/slots`

변경 없음(`source`가 응답에 추가될 뿐).

### `static/index.html`

시간표 폼 아래 `<input type=file>` + "미리보기" / "적용" 버튼 + 결과 `<pre>`. 스타일 0줄.

## 5. 영역별 영향

- `server/app/domain/csv_import.py` (신규): `parse(text, s) -> tuple[list[Row], list[RowError]]`, `apply(s, rows, dry_run) -> Summary`. 도메인 모델만 알고 `api`는 모른다 — 라우터가 enqueue를 호출.
- `server/app/domain/router.py`: `POST /import/slots`, `PUT /slots` 409.
- `server/app/schemas.py`: `SlotIn.source`, `ImportSummary`, `ImportError`.
- `server/app/domain/models.py` + `alembic/versions/web_slot_source_*.py`.
- `server/app/lora_service/api.py`: `enqueue_file_replace` (cw 리뷰). 기존 함수 변경 없음.
- `server/static/index.html`: 업로드 폼.
- `docs/specs/2026-09-09-roadmap-design.md` §4 계약 ⑤: "CSV = 이 spec §2.1" 링크 — cw 문서이므로 PR 본문에 반영 요청.
- modempi·firmware: 영향 없음(FILE은 기존 타입).

## 6. 무회귀 · 롤아웃

- 기존 65 테스트 그대로. `source` 기본값 2라 기존 `PUT` 호출·시드는 동작 동일.
- 마이그레이션은 additive(컬럼 추가). 다운그레이드는 컬럼 drop.
- 테스트:
  - 파서: 요일·시간·type 양식 두 가지씩, 바이트 초과, 없는 학교/건물/방, 파일 내 중복 키, 48 초과, 헤더 누락, BOM.
  - 적용: 삭제·갱신·삽입 카운트, `source≥2` skipped, 파일에 없는 방 불변, `dry_run` 무변경.
  - 라우터: 400이면 DB 불변·outbox 없음, 200이면 방마다 유닛 수만큼 FILE 행 + `room_versions.schedule` +1, `text/csv` 아닌 인코딩 400.
  - `enqueue_file_replace`: queued FILE이 이미 있어도 새 행(cw 리뷰 포인트).
  - `PUT` 409.

## 7. 역할 분담

| 누가 | 무엇 |
|---|---|
| wj | 전부 구현·테스트·문서 |
| cw | `api.enqueue_file_replace` 리뷰, 로드맵 계약 ⑤ 링크 반영 |
| mh | S4 "CSV 업로드" 화면 스펙에서 §4 응답 형식(요약·skipped·errors 표)을 참고 |

## 8. 성공 기준

- 우송대 E동 3개 방 60행 CSV → 200, 방마다 FILE 1세트, fake 허브에서 `job.payload.records` 60개 확인.
- 같은 파일 재업로드 → `added 0 updated 60 deleted 0`, FILE 다시 큐잉(내용 같아도 콘텐츠 FILE — 단순화, §9).
- 웹에서 한 슬롯을 `source=2`로 고친 뒤 재업로드 → 그 행 `skipped`, 슬롯 유지.
- 7행 오류 파일 → 400 + 7개 `errors`, DB·outbox 불변.

## 9. 열린 결정 (plan 단계에서 확정)

- 내용이 같은 재업로드도 `updated`로 세고 FILE을 보낸다. 변경 감지(필드 비교)는 코드 10줄이지만 "재업로드 = 재전송"이 관리자에게 더 예측 가능. 후속에 필요하면 추가.
- `enqueue_file_replace`의 위치: `api.py`(S2 spec §2.3의 v2 §8.6 목록에 없는 신규). 이슈 #10(api.py 분할)은 S4 때 — 지금은 `enqueue_full_sync` 바로 아래.
- `school` 컬럼은 이름 매칭. 학교가 1개인 전시 규모에서는 사실상 고정값이지만, 계약이라 넣는다(`bld` 글자가 학교 간 겹칠 수 있음 — S5 §9 파킹 항목과 같은 이유).
