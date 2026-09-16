# S2b — 시간표 CSV 임포트 구현 계획 (plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 생성일시: 2026-09-16
- 기준 spec: `docs/specs/2026-09-16-s2b-csv-import-design.md` (도메인·outbox는 `docs/specs/2026-09-14-s2-server-design.md`, FILE 의미 `docs/specs/2026-09-09-lora-v2-wor-design.md` §3.3)
- 담당: wj @leemonta9482. 브랜치 `feature/csv-import`. 커밋 scope `feat(server)`. PR은 사용자 지시 시.

**Goal:** 관리자가 CSV 한 장으로 여러 강의실의 정규 시간표를 넣으면, 출처 우선순위(포털 < 수동 < 긴급)를 지켜 `slots`를 교체하고 변경된 방마다 콘텐츠 FILE 1세트를 outbox에 넣는다.

**Architecture:** `server/app/domain/csv_import.py`(신규) 하나가 파싱·검증(`parse`)과 적용(`apply`)을 맡고 도메인 모델만 안다. 라우터가 `parse → dry_run이면 반환 → apply → commit → api.enqueue_file_replace(방마다)`를 잇는다. `slots.source` 컬럼(마이그레이션 `web_slot_source`)이 우선순위의 근거. `lora_service/api.py`에는 콘텐츠 FILE 함수 하나만 추가(cw 리뷰).

**Tech Stack:** Python 3.12 · uv · FastAPI 0.141 · SQLAlchemy 2 · Alembic · pydantic 2 · `csv`(stdlib) · pytest · ruff

**Spec:** `docs/specs/2026-09-16-s2b-csv-import-design.md`

## Global Constraints

- CSV: UTF-8(BOM 허용), 헤더 필수, 컬럼 이름 매칭(순서 무관·대소문자 무관·앞뒤 공백 무시), 필수 컬럼 `school,building,room,day,start,end,type,subject,professor`. `day` = `월화수목금토일` 또는 `1~7`. `type` = `수업 시험 휴강 빈강의실 특강 대여` 또는 `1~6`. `start/end` = `HH:MM`(`H:MM` 허용), `end > start`. `subject` ≤ `P.SUBJ_MAX`(20) B, `professor` ≤ `P.PROF_MAX`(12) B (UTF-8). 빈 행 건너뜀. `professor` 빈 값 허용.
- `building`은 `buildings.bld` **글자 1자**. 없는 학교/건물/방은 오류(자동 생성 안 함). 파일 내 같은 방 `(day,start)` 중복 오류. 방당 `포털 행 + 남는 source≥2 슬롯` > 48 오류. 오류는 최대 100개까지 모아 400. `row`는 헤더 = 1인 파일 행 번호. 헤더 누락은 `row: 0`.
- `slots.source`: 1=포털 2=수동 3=긴급, `NOT NULL DEFAULT 2`. 낮은 출처는 높은 출처를 못 덮는다 — CSV는 `source≥2` 키를 `skipped`, `PUT`은 `existing.source > body.source`면 409. `DELETE`는 출처 무시.
- 적용: 파일에 나온 방만. 방마다 파일에 없는 `source=1` 삭제, 겹치는 상위 출처는 skipped, 나머지 갱신/삽입. 같은 내용 재업로드도 `updated`. 변경 0인 방은 FILE 안 보냄.
- 순서: `parse`(DB 읽기만) → `dry_run`이면 반환 → `apply` → `s.commit()` → 방마다 `api.enqueue_file_replace(bld, room, "schedule")`. RecordProvider가 커밋된 DB를 읽기 때문. enqueue 실패 → 500 + `"DB 는 반영됨 — POST /api/rooms/{id}/sync 로 재전송"`.
- `POST /api/import/slots?dry_run=false`, 본문 = CSV 텍스트(`text/csv`), multipart 아님, `python-multipart` 추가 금지. 1 MiB 초과 413. UTF-8 디코드 실패 400 `"UTF-8 로 저장하세요"`.
- `enqueue_file_replace(bld, room, kind, unit=0)`: 버전 +1, 현재 레코드로 FILE 새로 만들어 유닛별 삽입, 기존 queued FILE 재사용 안 함. 기존 `enqueue_full_sync` 동작 변경 금지. `lora_service/api.py`는 cw 필수 리뷰 — 이 함수 외에 손대지 않는다.
- `lora_proto/` 수정 금지. 마이그레이션 additive만. 기존 65 테스트 그대로 통과.
- uv only; ruff line-length 100/py312; 모든 명령은 `server/`에서. 커밋 `feat(server): ...`, AI 표기 없음.

---

## 파일 구조

```
server/app/domain/models.py            Slot.source 컬럼                       (Task 1)
server/alembic/versions/web_slot_source_<rev>.py  ALTER slots ADD source     (Task 1)
server/app/schemas.py                  SlotIn.source, ImportSummary/ImportErrors (Task 1, 5)
server/app/domain/router.py            PUT 409, POST /import/slots           (Task 1, 5)
server/app/lora_service/api.py         enqueue_file_replace                  (Task 2)
server/app/domain/csv_import.py        parse / apply                         (Task 3, 4)
server/static/index.html               업로드 폼                              (Task 5)
server/README.md, docs/progress.html   문서·진행도                            (Task 6)
server/tests/test_migrations.py        source 컬럼                            (Task 1)
server/tests/test_domain.py            PUT 409                               (Task 1)
server/tests/test_api_enqueue.py       file_replace                          (Task 2)
server/tests/test_csv_import.py        parse / apply / 라우터                 (Task 3, 4, 5)
```

---

### Task 1: `slots.source` — 모델·마이그레이션·`PUT` 409

**Files:**
- Modify: `server/app/domain/models.py` (`class Slot`)
- Create: `server/alembic/versions/web_slot_source_<rev>.py` (alembic이 rev를 만든다)
- Modify: `server/app/schemas.py` (`SlotIn`, `SlotOut`)
- Modify: `server/app/domain/router.py` (`put_slot`)
- Test: `server/tests/test_migrations.py`, `server/tests/test_domain.py`

**Interfaces:**
- Produces: `Slot.source: int` (1/2/3), `SlotIn.source: int = 2`, `SlotOut.source`. `PUT /api/rooms/{id}/slots` 409 규칙.

- [ ] **Step 1: 실패 테스트 — 마이그레이션에 `source` 컬럼**

`server/tests/test_migrations.py` 끝에 추가:

```python
def test_slot_source_column(tmp_path):
    db = tmp_path / "s.db"
    _upgrade(db)
    cols = {c["name"]: c for c in inspect(create_engine(f"sqlite:///{db}")).get_columns("slots")}
    assert cols["source"]["nullable"] is False and cols["source"]["default"] == "2"
```

- [ ] **Step 2: 실패 테스트 — `PUT` 출처 규칙**

`server/tests/test_domain.py` 끝에 추가:

```python
def test_put_slot_source_default_and_409_on_downgrade(client):
    _sch, _b, r = _setup(client)
    body = {"day": 2, "s_h": 9, "s_m": 0, "e_h": 10, "e_m": 0, "type": 1, "subject": "a", "professor": ""}
    assert client.put(f"/api/rooms/{r['id']}/slots", json=body).status_code == 200
    assert client.get(f"/api/rooms/{r['id']}/slots").json()[0]["source"] == 2
    # 긴급으로 올리기 (2 → 3) 허용
    assert client.put(f"/api/rooms/{r['id']}/slots", json={**body, "type": 3, "source": 3}).status_code == 200
    assert client.get(f"/api/rooms/{r['id']}/slots").json()[0]["source"] == 3
    # 수동(기본 2)·포털(1)로 덮기 → 409
    assert client.put(f"/api/rooms/{r['id']}/slots", json=body).status_code == 409
    assert client.put(f"/api/rooms/{r['id']}/slots", json={**body, "source": 1}).status_code == 409
    assert client.get(f"/api/rooms/{r['id']}/slots").json()[0]["type"] == 3  # 그대로
    # 삭제는 출처 무시
    assert client.delete(f"/api/rooms/{r['id']}/slots/2/9/0").status_code == 200
    assert client.get(f"/api/rooms/{r['id']}/slots").json() == []
    # 범위 밖 source
    assert client.put(f"/api/rooms/{r['id']}/slots", json={**body, "source": 4}).status_code == 422
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_migrations.py::test_slot_source_column tests/test_domain.py::test_put_slot_source_default_and_409_on_downgrade -q`
Expected: FAIL (`KeyError: 'source'`, `assert 422 == 200` 등)

- [ ] **Step 4: 모델**

`server/app/domain/models.py` `class Slot`의 `professor` 줄 아래:

```python
    source: Mapped[int] = mapped_column(default=2, server_default="2")  # 1=포털 2=수동 3=긴급 (S2b §2.2)
```

- [ ] **Step 5: 마이그레이션**

Run: `uv run alembic revision -m "web_slot_source"` → 생성된 파일을 `server/alembic/versions/web_slot_source_<rev>.py`로 두고 본문을:

```python
"""web_slot_source

Revision ID: <rev>
Revises: b3914933fd2a
Create Date: <그대로>

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "<rev>"
down_revision: str | Sequence[str] | None = "b3914933fd2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 기존 행은 2(수동) — 포털 재업로드가 기존 데이터를 지우지 않도록 (S2b §2.2)
    op.add_column("slots", sa.Column("source", sa.Integer(), nullable=False, server_default="2"))


def downgrade() -> None:
    with op.batch_alter_table("slots") as b:
        b.drop_column("source")
```

`down_revision`이 `b3914933fd2a`(web_init)인지 확인.

- [ ] **Step 6: 스키마·라우터**

`server/app/schemas.py`:

```python
class SlotIn(_Span):
    day: int = Field(ge=1, le=7)
    source: int = Field(2, ge=1, le=3)  # 1=포털 2=수동 3=긴급 (S2b §2.2)
```

`SlotOut`은 `SlotIn`을 상속하므로 자동으로 `source` 노출.

`server/app/domain/router.py` `put_slot`: `obj` 조회 뒤, `if obj is None:` 앞에:

```python
    if obj is not None and obj.source > body.source:
        raise HTTPException(409, f"source {obj.source} 슬롯은 source ≥ {obj.source} 로만 수정")
```

`for k, v in body.model_dump().items(): setattr(obj, k, v)`가 `source`도 저장한다 — 추가 코드 없음. `api.enqueue_slot_set` 호출은 그대로(`source`는 노드에 안 간다).

- [ ] **Step 7: 통과 확인 + 전체**

Run: `uv run pytest -q` → 67 passed. `uv run ruff check . && uv run ruff format --check .`

- [ ] **Step 8: 커밋**

```bash
git add app/domain/models.py alembic/versions/ app/schemas.py app/domain/router.py tests/test_migrations.py tests/test_domain.py
git commit -m "feat(server): slots.source 출처 컬럼 (1 포털·2 수동·3 긴급) — PUT 은 낮은 출처로 못 덮음(409)"
```

---

### Task 2: `api.enqueue_file_replace` — 콘텐츠 FILE (cw 리뷰)

**Files:**
- Modify: `server/app/lora_service/api.py` (`enqueue_full_sync` 바로 아래)
- Test: `server/tests/test_api_enqueue.py`

**Interfaces:**
- Consumes: `_room`, `_Session`, `_bump_ver`, `_records`, `_insert`, `FILE_KIND`, `C.build_file`, `_hub.notify` (모두 `api.py` 안에 있음).
- Produces: `enqueue_file_replace(bld: str, room: int, kind: str, unit: int = 0) -> list[int]`.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_api_enqueue.py` `test_full_sync_dedupes_per_unit` 아래:

```python
def test_file_replace_bumps_ver_and_never_reuses_queued(db, hub):
    api.set_record_provider(
        lambda bld, room, kind: (
            [C.SlotSet(0, 1, 9, 0, 10, 0, 1, "a", "b")] if kind == "schedule" else []
        )
    )
    stale = api.enqueue_full_sync("E", 301, kinds=("schedule",))  # 재동기 FILE, ver 1, 유닛 2개
    ids = api.enqueue_file_replace("E", 301, "schedule")
    assert len(ids) == 2 and not set(ids) & set(stale)  # 재사용 안 함
    rows = {r.id: r for r in _rows(db)}
    assert all(rows[i].type == "FILE" and rows[i].new_ver == 2 for i in ids)
    assert {rows[i].unit for i in ids} == {1, 2}
    assert json.loads(rows[ids[0]].payload)["records"][0]["subject"] == "a"
    with db() as s:
        assert s.get(RoomVersion, ("E", 301, "schedule")).ver == 2
    again = api.enqueue_file_replace("E", 301, "schedule")
    assert not set(again) & set(ids) and _rows(db)[-1].new_ver == 3
    assert hub.notified[-1] == "m1"


def test_file_replace_unknown_room_and_bad_kind(db):
    with pytest.raises(LookupError):
        api.enqueue_file_replace("E", 999, "schedule")
    with pytest.raises(KeyError):
        api.enqueue_file_replace("E", 301, "bogus")
```

`_room`이 없는 방에 무엇을 던지는지 확인(`test_unknown_room_raises_not_found` 참고)하고 `pytest.raises`의 타입을 그것에 맞춘다.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_api_enqueue.py -k file_replace -q`
Expected: FAIL `AttributeError: module 'app.lora_service.api' has no attribute 'enqueue_file_replace'`

- [ ] **Step 3: 구현**

`server/app/lora_service/api.py`, `enqueue_full_sync` 바로 아래:

```python
def enqueue_file_replace(bld: str, room: int, kind: str, unit: int = 0) -> list[int]:
    """콘텐츠 변경 FILE (S2b §2.4): kind 버전 +1, 현재 RecordProvider 레코드로 FILE 을 새로 만들어
    유닛별 삽입. 재동기 FILE(enqueue_full_sync — bump 없음·queued 재사용)과 달리 기존 queued FILE 을
    재사용하지 않는다 — 임포트 직후 옛 내용의 FILE 이 나가고 새 내용이 영영 안 가는 것을 막는다.
    호출 측은 레코드가 커밋된 뒤에 부른다(RecordProvider 는 자기 세션으로 읽는다)."""
    info = _room(bld, room)
    file_kind = FILE_KIND[kind]
    with _Session() as s, s.begin():
        new_ver = _bump_ver(s, bld, room, kind)
        records = _records(bld, room, kind)
        C.build_file(file_kind, records, new_ver)  # 크기·kind 검증 — 실패면 롤백(버전도)
        payload = json.dumps(
            {"kind": file_kind, "records": [jsonio.to_json(r, drop=("new_ver",)) for r in records]},
            ensure_ascii=False,
        )
        ids = _insert(s, info, bld, room, unit, "FILE", payload, new_ver)
    if info.modem_id:
        _hub.notify(info.modem_id)
    return ids
```

payload 구성이 `_enqueue_file`과 같은 3줄이다 — 두 곳을 `_file_payload(file_kind, records)` 헬퍼로 묶어도 되지만 `_enqueue_file`을 건드리면 cw 리뷰 범위가 늘어난다. **이번엔 복제한다**(§9 이슈 #10 분할 때 정리).

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q` → 69 passed. ruff.

- [ ] **Step 5: 커밋**

```bash
git add app/lora_service/api.py tests/test_api_enqueue.py
git commit -m "feat(server): enqueue_file_replace — 콘텐츠 변경 FILE (ver+1, queued 재사용 안 함)"
```

---

### Task 3: `csv_import.parse` — 파싱·검증

**Files:**
- Create: `server/app/domain/csv_import.py`
- Test: `server/tests/test_csv_import.py`

**Interfaces:**
- Consumes: `School, Building, Room, Slot` 모델, `P.SUBJ_MAX/P.PROF_MAX`.
- Produces:

```python
@dataclass(frozen=True)
class Row:
    row: int            # 파일 행 번호 (헤더 = 1)
    room_id: int
    bld: str
    room: int
    day: int; s_h: int; s_m: int; e_h: int; e_m: int; type: int
    subject: str; professor: str

@dataclass(frozen=True)
class RowError:
    row: int
    error: str

MAX_ERRORS = 100
NODE_SLOT_MAX = 48
def parse(text: str, s: Session) -> tuple[list[Row], list[RowError]]
```

`errors`가 비어 있지 않으면 `rows`는 신뢰하지 않는다(라우터는 400).

- [ ] **Step 1: 실패 테스트**

`server/tests/test_csv_import.py` 신규:

```python
import pytest
from sqlalchemy import select

from app.domain import csv_import as CI
from app.domain.models import Building, Room, School, Slot
from app.lora_service.models import Modem

HEADER = "school,building,room,day,start,end,type,subject,professor\n"


@pytest.fixture
def seeded(app):
    """명지 E동 301(units=2)·302(units=1). 301 에 수동 슬롯 월 09:00, 긴급 슬롯 화 09:00."""
    with app.state.Session() as s, s.begin():
        s.add(Modem(modem_id="mjc-eng", token_hash="x"))
        sch = School(name="명지", net_id=0x4B)
        s.add(sch)
        s.flush()
        b = Building(school_id=sch.id, name="공학관", bld="E", modem_id="mjc-eng")
        s.add(b)
        s.flush()
        r1 = Room(building_id=b.id, room=301, units=2)
        r2 = Room(building_id=b.id, room=302, units=1)
        s.add_all([r1, r2])
        s.flush()
        s.add(Slot(room_id=r1.id, day=1, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="수동", professor="", source=2))
        s.add(Slot(room_id=r1.id, day=2, s_h=9, s_m=0, e_h=10, e_m=0, type=3, subject="휴강", professor="", source=3))
        ids = (r1.id, r2.id)
    return ids


def _parse(app, text):
    with app.state.Session() as s:
        return CI.parse(text, s)


def test_parse_ok_both_notations(app, seeded):
    r1, r2 = seeded
    text = HEADER + (
        "명지,E,301,수,09:00,10:30,수업,자료구조,김\n"
        " 명지 , E , 302 , 3 , 9:00 , 10:30 , 1 , 자료구조 , 김 \n"
        "\n"
        "명지,E,302,일,13:00,14:50,대여,,\n"
    )
    rows, errors = _parse(app, text)
    assert errors == []
    assert [(r.row, r.room_id, r.day, r.s_h, r.s_m, r.e_h, r.e_m, r.type, r.subject, r.professor) for r in rows] == [
        (2, r1, 3, 9, 0, 10, 30, 1, "자료구조", "김"),
        (3, r2, 3, 9, 0, 10, 30, 1, "자료구조", "김"),
        (5, r2, 7, 13, 0, 14, 50, 6, "", ""),
    ]
    assert rows[0].bld == "E" and rows[0].room == 301


def test_parse_bom_and_header_case_order(app, seeded):
    text = "﻿Professor, Subject ,TYPE,end,start,day,room,building,school\n김,자료구조,수업,10:30,09:00,월,302,E,명지\n"
    rows, errors = _parse(app, text)
    assert errors == [] and rows[0].day == 1 and rows[0].subject == "자료구조"


def test_parse_missing_header_is_row0(app, seeded):
    rows, errors = _parse(app, "school,building,room,day,start,end,type,subject\n명지,E,301,월,09:00,10:00,1,a\n")
    assert rows == [] and errors == [CI.RowError(0, "헤더에 없는 컬럼: professor")]


@pytest.mark.parametrize(
    "line,msg",
    [
        ("서울대,E,301,월,09:00,10:00,1,a,", "school: '서울대' 없음"),
        ("명지,Z,301,월,09:00,10:00,1,a,", "building: 'Z' 없음 (명지)"),
        ("명지,E,999,월,09:00,10:00,1,a,", "room: 999 없음 (명지 E)"),
        ("명지,E,abc,월,09:00,10:00,1,a,", "room: 'abc' 은 1~9999"),
        ("명지,E,301,월요일,09:00,10:00,1,a,", "day: '월요일' 은 월~일 또는 1~7"),
        ("명지,E,301,8,09:00,10:00,1,a,", "day: '8' 은 월~일 또는 1~7"),
        ("명지,E,301,월,9시,10:00,1,a,", "start: '9시' 은 HH:MM"),
        ("명지,E,301,월,09:00,24:00,1,a,", "end: '24:00' 은 HH:MM"),
        ("명지,E,301,월,10:00,09:00,1,a,", "end 09:00 ≤ start 10:00"),
        ("명지,E,301,월,09:00,09:00,1,a,", "end 09:00 ≤ start 09:00"),
        ("명지,E,301,월,09:00,10:00,실습,a,", "type: '실습' 은 수업~대여 또는 1~6"),
        ("명지,E,301,월,09:00,10:00,7,a,", "type: '7' 은 수업~대여 또는 1~6"),
        ("명지,E,301,월,09:00,10:00,1,가나다라마바사,", "subject 21 B > 20 B (UTF-8)"),
        ("명지,E,301,월,09:00,10:00,1,a,가나다라마", "professor 15 B > 12 B (UTF-8)"),
    ],
)
def test_parse_row_errors(app, seeded, line, msg):
    rows, errors = _parse(app, HEADER + line + "\n")
    assert errors == [CI.RowError(2, msg)]


def test_parse_collects_all_errors_up_to_100(app, seeded):
    text = HEADER + "".join("명지,E,301,9,09:00,10:00,1,a,\n" for _ in range(150))
    _rows, errors = _parse(app, text)
    assert len(errors) == 100 and errors[0].row == 2 and errors[-1].row == 101


def test_parse_duplicate_key_in_file(app, seeded):
    text = HEADER + "명지,E,301,월,09:00,10:00,1,a,\n명지,E,302,월,09:00,10:00,1,a,\n명지,E,301,1,9:00,11:00,2,b,\n"
    _rows, errors = _parse(app, text)
    assert errors == [CI.RowError(4, "row 2 와 중복 (301 월 09:00)")]


def test_parse_node_slot_cap_counts_surviving_higher_source(app, seeded):
    # 301 에 source≥2 슬롯 2개(월 09:00, 화 09:00). 포털 47행(월 09:00 겹침 1 포함) →
    # 겹치는 1행은 skip 이라 46 + 2 = 48 → OK. 48행이면 47 + 2 = 49 → 오류.
    def lines(n):
        out = ["명지,E,301,월,09:00,10:00,1,a,"]  # 겹침
        h = 10
        d = 1
        while len(out) < n:
            out.append(f"명지,E,301,{d},{h:02d}:00,{h:02d}:30,1,a,")
            h += 1
            if h == 23:
                h, d = 10, d + 1
        return "".join(x + "\n" for x in out)

    assert _parse(app, HEADER + lines(47))[1] == []
    _rows, errors = _parse(app, HEADER + lines(48))
    assert errors == [CI.RowError(0, "301: 슬롯 49 개 > 48 (노드 상한)")]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_csv_import.py -q`
Expected: FAIL `ModuleNotFoundError: app.domain.csv_import`

- [ ] **Step 3: 구현**

`server/app/domain/csv_import.py`:

```python
"""시간표 CSV 임포트 (S2b spec §2). 도메인 모델만 안다 — outbox 는 라우터가 넣는다."""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass

from lora_proto import proto as P
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Building, Room, School, Slot

COLUMNS = ("school", "building", "room", "day", "start", "end", "type", "subject", "professor")
DAYS = "월화수목금토일"
TYPES = ("수업", "시험", "휴강", "빈강의실", "특강", "대여")
MAX_ERRORS = 100
NODE_SLOT_MAX = 48  # v2 §12
_HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class Row:
    row: int  # 파일 행 번호 (헤더 = 1)
    room_id: int
    bld: str
    room: int
    day: int
    s_h: int
    s_m: int
    e_h: int
    e_m: int
    type: int
    subject: str
    professor: str


@dataclass(frozen=True)
class RowError:
    row: int
    error: str


def _day(v: str) -> int | None:
    if len(v) == 1 and v in DAYS:
        return DAYS.index(v) + 1
    return int(v) if v.isdigit() and 1 <= int(v) <= 7 else None


def _type(v: str) -> int | None:
    if v in TYPES:
        return TYPES.index(v) + 1
    return int(v) if v.isdigit() and 1 <= int(v) <= 6 else None


def _hhmm(v: str) -> tuple[int, int] | None:
    m = _HHMM.match(v)
    if not m:
        return None
    h, mi = int(m[1]), int(m[2])
    return (h, mi) if h <= 23 and mi <= 59 else None


def _bytes(s: str) -> int:
    return len(s.encode("utf-8"))


class _Lookup:
    """학교 이름 → bld → room 번호 → (room_id, bld, room). 한 번 읽어 dict 로."""

    def __init__(self, s: Session):
        self.rooms: dict[tuple[str, str, int], int] = {}
        self.schools: set[str] = set()
        self.blds: set[tuple[str, str]] = set()
        q = (
            select(School.name, Building.bld, Room.room, Room.id)
            .join(Building, Building.school_id == School.id)
            .join(Room, Room.building_id == Building.id)
        )
        for name, bld, room, rid in s.execute(q):
            self.rooms[(name, bld, room)] = rid
        for name, bld in s.execute(select(School.name, Building.bld).join(Building)):
            self.schools.add(name)
            self.blds.add((name, bld))
        for name in s.scalars(select(School.name)):
            self.schools.add(name)


def _row(n: int, rec: dict[str, str], lk: _Lookup) -> Row | RowError:
    school, bld = rec["school"], rec["building"]
    if school not in lk.schools:
        return RowError(n, f"school: '{school}' 없음")
    if (school, bld) not in lk.blds:
        return RowError(n, f"building: '{bld}' 없음 ({school})")
    if not (rec["room"].isdigit() and 1 <= int(rec["room"]) <= 9999):
        return RowError(n, f"room: '{rec['room']}' 은 1~9999")
    room = int(rec["room"])
    rid = lk.rooms.get((school, bld, room))
    if rid is None:
        return RowError(n, f"room: {room} 없음 ({school} {bld})")
    day = _day(rec["day"])
    if day is None:
        return RowError(n, f"day: '{rec['day']}' 은 월~일 또는 1~7")
    start, end = _hhmm(rec["start"]), _hhmm(rec["end"])
    if start is None:
        return RowError(n, f"start: '{rec['start']}' 은 HH:MM")
    if end is None:
        return RowError(n, f"end: '{rec['end']}' 은 HH:MM")
    if end <= start:
        return RowError(n, f"end {end[0]:02d}:{end[1]:02d} ≤ start {start[0]:02d}:{start[1]:02d}")
    type_ = _type(rec["type"])
    if type_ is None:
        return RowError(n, f"type: '{rec['type']}' 은 수업~대여 또는 1~6")
    if _bytes(rec["subject"]) > P.SUBJ_MAX:
        return RowError(n, f"subject {_bytes(rec['subject'])} B > {P.SUBJ_MAX} B (UTF-8)")
    if _bytes(rec["professor"]) > P.PROF_MAX:
        return RowError(n, f"professor {_bytes(rec['professor'])} B > {P.PROF_MAX} B (UTF-8)")
    return Row(n, rid, bld, room, day, *start, *end, type_, rec["subject"], rec["professor"])


def parse(text: str, s: Session) -> tuple[list[Row], list[RowError]]:
    """CSV 텍스트 → Row 목록. errors 가 비어 있지 않으면 rows 는 쓰지 않는다 (all-or-nothing)."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    header = [h.strip().lower() for h in next(reader, [])]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        return [], [RowError(0, f"헤더에 없는 컬럼: {', '.join(missing)}")]
    idx = {c: header.index(c) for c in COLUMNS}
    lk = _Lookup(s)
    rows: list[Row] = []
    errors: list[RowError] = []
    seen: dict[tuple[int, int, int, int], int] = {}  # (room_id, day, s_h, s_m) → row
    for n, raw in enumerate(reader, start=2):
        if not any(c.strip() for c in raw):
            continue
        if len(errors) >= MAX_ERRORS:
            break
        rec = {c: (raw[i].strip() if i < len(raw) else "") for c, i in idx.items()}
        r = _row(n, rec, lk)
        if isinstance(r, RowError):
            errors.append(r)
            continue
        key = (r.room_id, r.day, r.s_h, r.s_m)
        if key in seen:
            errors.append(RowError(n, f"row {seen[key]} 와 중복 ({r.room} {DAYS[r.day - 1]} {r.s_h:02d}:{r.s_m:02d})"))
            continue
        seen[key] = n
        rows.append(r)
    if errors:
        return rows, errors
    # 노드 슬롯 상한: 포털 행 + 그 방에 남을 source≥2 슬롯 (겹치는 키는 포털 행이 skip 되므로 한 번만)
    by_room: dict[int, set[tuple[int, int, int]]] = defaultdict(set)
    for r in rows:
        by_room[r.room_id].add((r.day, r.s_h, r.s_m))
    for rid, keys in by_room.items():
        kept = s.scalars(select(Slot).where(Slot.room_id == rid, Slot.source >= 2)).all()
        total = len(keys | {(x.day, x.s_h, x.s_m) for x in kept})
        if total > NODE_SLOT_MAX:
            room_no = next(r.room for r in rows if r.room_id == rid)
            errors.append(RowError(0, f"{room_no}: 슬롯 {total} 개 > {NODE_SLOT_MAX} (노드 상한)"))
    return rows, errors
```

`_Lookup`의 세 쿼리는 한 번씩만 돈다. `rooms` 쿼리에서 `schools`·`blds`도 채울 수 있지만 방이 없는 건물/학교는 거기 안 나오므로 따로 읽는다.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_csv_import.py -q` → 전부 PASS. `uv run ruff check . && uv run ruff format --check .` (ruff가 긴 f-string 줄을 지적하면 줄바꿈).

- [ ] **Step 5: 커밋**

```bash
git add app/domain/csv_import.py tests/test_csv_import.py
git commit -m "feat(server): csv_import.parse — 계약 ⑤ CSV 파싱·검증 (요일·시간·type 양식, 출처·상한 검사)"
```

---

### Task 4: `csv_import.apply` — 방별 포털 슬롯 교체

**Files:**
- Modify: `server/app/domain/csv_import.py`
- Test: `server/tests/test_csv_import.py`

**Interfaces:**
- Consumes: `Row`, `Slot`.
- Produces:

```python
@dataclass
class Summary:
    rooms: int = 0
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: list[dict] = field(default_factory=list)   # [{"row": n, "reason": str}]
    changed: list[tuple[str, int]] = field(default_factory=list)  # (bld, room) — 변경 있는 방, FILE 대상

def apply(rows: list[Row], s: Session, dry_run: bool = False) -> Summary
```

`dry_run=True`면 세션에 아무것도 쓰지 않는다(카운트만). 커밋은 호출 측.

- [ ] **Step 1: 실패 테스트**

`server/tests/test_csv_import.py` 끝에:

```python
def _slots(app, rid):
    with app.state.Session() as s:
        return [
            (x.day, x.s_h, x.s_m, x.subject, x.source)
            for x in s.scalars(select(Slot).where(Slot.room_id == rid).order_by(Slot.day, Slot.s_h))
        ]


def test_apply_replaces_portal_keeps_higher_source(app, seeded):
    r1, r2 = seeded
    with app.state.Session() as s, s.begin():
        s.add(Slot(room_id=r1, day=3, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="옛포털", professor="", source=1))
        s.add(Slot(room_id=r1, day=4, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="유지될포털", professor="", source=1))
        s.add(Slot(room_id=r2, day=1, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="302포털", professor="", source=1))
    text = HEADER + (
        "명지,E,301,월,09:00,10:00,수업,포털월,\n"      # 수동(source 2) 과 겹침 → skipped
        "명지,E,301,화,09:00,10:00,수업,포털화,\n"      # 긴급(source 3) 과 겹침 → skipped
        "명지,E,301,목,09:00,10:00,수업,갱신됨,\n"      # 기존 포털 갱신
        "명지,E,301,금,09:00,10:00,수업,새로,\n"        # 삽입
    )                                                  # 수 09:00 옛포털 → 삭제. 302 는 파일에 없음 → 불변
    with app.state.Session() as s, s.begin():
        rows, errors = CI.parse(text, s)
        assert errors == []
        summary = CI.apply(rows, s)
    assert (summary.rooms, summary.added, summary.updated, summary.deleted) == (1, 1, 1, 1)
    assert summary.skipped == [
        {"row": 2, "reason": "수동 슬롯 있음 (source=2)"},
        {"row": 3, "reason": "긴급 슬롯 있음 (source=3)"},
    ]
    assert summary.changed == [("E", 301)]
    assert _slots(app, r1) == [
        (1, 9, 0, "수동", 2),
        (2, 9, 0, "휴강", 3),
        (4, 9, 0, "갱신됨", 1),
        (5, 9, 0, "새로", 1),
    ]
    assert _slots(app, r2) == [(1, 9, 0, "302포털", 1)]


def test_apply_same_file_twice_counts_updated_and_still_changed(app, seeded):
    _r1, r2 = seeded
    text = HEADER + "명지,E,302,월,09:00,10:00,수업,a,\n"
    for expect in ((1, 0), (0, 1)):  # (added, updated)
        with app.state.Session() as s, s.begin():
            rows, _ = CI.parse(text, s)
            sm = CI.apply(rows, s)
        assert (sm.added, sm.updated, sm.deleted) == (*expect, 0) and sm.changed == [("E", 302)]
    assert _slots(app, r2) == [(1, 9, 0, "a", 1)]


def test_apply_no_change_room_not_in_changed(app, seeded):
    # 302 의 유일한 행이 수동 슬롯과 겹쳐 skipped → 변경 0 → changed 에 없음, rooms 0
    r1, r2 = seeded
    with app.state.Session() as s, s.begin():
        s.add(Slot(room_id=r2, day=1, s_h=9, s_m=0, e_h=10, e_m=0, type=1, subject="수동302", professor="", source=2))
    text = HEADER + "명지,E,302,월,09:00,10:00,수업,a,\n"
    with app.state.Session() as s, s.begin():
        rows, _ = CI.parse(text, s)
        sm = CI.apply(rows, s)
    assert sm.rooms == 0 and sm.changed == [] and len(sm.skipped) == 1


def test_apply_dry_run_writes_nothing(app, seeded):
    r1, _r2 = seeded
    text = HEADER + "명지,E,301,금,09:00,10:00,수업,새로,\n"
    with app.state.Session() as s, s.begin():
        rows, _ = CI.parse(text, s)
        sm = CI.apply(rows, s, dry_run=True)
    assert sm.added == 1 and sm.changed == [("E", 301)]
    assert _slots(app, r1) == [(1, 9, 0, "수동", 2), (2, 9, 0, "휴강", 3)]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_csv_import.py -k apply -q`
Expected: FAIL `AttributeError: module ... has no attribute 'apply'`

- [ ] **Step 3: 구현**

`server/app/domain/csv_import.py`에 추가 (`from dataclasses import dataclass, field`, `from sqlalchemy import delete, select`):

```python
SOURCE_NAME = {1: "포털", 2: "수동", 3: "긴급"}


@dataclass
class Summary:
    rooms: int = 0
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: list[dict] = field(default_factory=list)
    changed: list[tuple[str, int]] = field(default_factory=list)  # FILE 대상 (bld, room)


def apply(rows: list[Row], s: Session, dry_run: bool = False) -> Summary:
    """방마다 source=1 슬롯을 파일 내용으로 교체 (S2b §2.3). 커밋은 호출 측. dry_run 이면 세지만 쓰지 않는다."""
    sm = Summary()
    by_room: dict[int, list[Row]] = defaultdict(list)
    for r in rows:
        by_room[r.room_id].append(r)
    for rid, rs in by_room.items():
        existing = {
            (x.day, x.s_h, x.s_m): x for x in s.scalars(select(Slot).where(Slot.room_id == rid))
        }
        file_keys = {(r.day, r.s_h, r.s_m) for r in rs}
        changed = False
        for key, x in existing.items():
            if x.source == 1 and key not in file_keys:
                sm.deleted += 1
                changed = True
                if not dry_run:
                    s.delete(x)
        for r in rs:
            x = existing.get((r.day, r.s_h, r.s_m))
            if x is not None and x.source >= 2:
                sm.skipped.append({"row": r.row, "reason": f"{SOURCE_NAME[x.source]} 슬롯 있음 (source={x.source})"})
                continue
            changed = True
            if x is None:
                sm.added += 1
                x = Slot(room_id=rid, day=r.day, s_h=r.s_h, s_m=r.s_m, source=1)
                if not dry_run:
                    s.add(x)
            else:
                sm.updated += 1
            if not dry_run:
                x.e_h, x.e_m, x.type, x.subject, x.professor = r.e_h, r.e_m, r.type, r.subject, r.professor
        if changed:
            sm.rooms += 1
            sm.changed.append((rs[0].bld, rs[0].room))
    if not dry_run:
        s.flush()
    return sm
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q` → 전부 PASS. ruff.

- [ ] **Step 5: 커밋**

```bash
git add app/domain/csv_import.py tests/test_csv_import.py
git commit -m "feat(server): csv_import.apply — 방별 포털 슬롯 교체, 수동·긴급 유지(skipped), dry_run"
```

---

### Task 5: `POST /api/import/slots` + 스키마 + 정적 폼

**Files:**
- Modify: `server/app/schemas.py` (`ImportSummary`, `ImportErrors`)
- Modify: `server/app/domain/router.py` (엔드포인트)
- Modify: `server/static/index.html`
- Test: `server/tests/test_csv_import.py`

**Interfaces:**
- Consumes: `csv_import.parse/apply/Summary/RowError`, `api.enqueue_file_replace`.
- Produces: `POST /api/import/slots?dry_run=false` (S2b §4).

- [ ] **Step 1: 실패 테스트**

`server/tests/test_csv_import.py` 끝에 (상단 import에 `import json`, `from app.lora_service.models import Outbox, RoomVersion` 추가):

```python
def _post(client, text, **params):
    return client.post(
        "/api/import/slots", params=params, content=text.encode("utf-8"),
        headers={"content-type": "text/csv; charset=utf-8"},
    )


def _outbox(app):
    with app.state.Session() as s:
        return s.scalars(select(Outbox).order_by(Outbox.id)).all()


def test_import_400_leaves_db_and_outbox_untouched(client, app, seeded):
    r1, _ = seeded
    text = HEADER + "명지,E,301,금,09:00,10:00,수업,새로,\n명지,E,301,토,25:00,10:00,수업,x,\n"
    res = _post(client, text)
    assert res.status_code == 400
    assert res.json() == {"errors": [{"row": 3, "error": "start: '25:00' 은 HH:MM"}]}
    assert len(_slots(app, r1)) == 2 and _outbox(app) == []


def test_import_200_creates_file_per_unit_and_bumps_ver(client, app, seeded):
    r1, r2 = seeded
    text = HEADER + (
        "명지,E,301,월,09:00,10:00,수업,포털월,\n"   # 수동과 겹침 → skipped
        "명지,E,301,금,09:00,10:00,수업,새로,\n"
        "명지,E,302,월,09:00,10:00,수업,302,\n"
    )
    res = _post(client, text)
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["rooms"], body["added"], body["updated"], body["deleted"]) == (2, 2, 0, 0)
    assert body["skipped"] == [{"row": 2, "reason": "수동 슬롯 있음 (source=2)"}]
    rows = _outbox(app)
    assert [x.id for x in rows] == body["outbox_ids"] and len(rows) == 3  # 301 유닛 2 + 302 유닛 1
    assert all(x.type == "FILE" and x.new_ver == 1 for x in rows)
    recs = json.loads(rows[0].payload)["records"]
    assert [r["subject"] for r in recs] == ["수동", "휴강", "새로"]  # 커밋된 DB 를 읽음
    with app.state.Session() as s:
        assert s.get(RoomVersion, ("E", 301, "schedule")).ver == 1
    # 재업로드: updated, ver 2, FILE 다시
    res = _post(client, text)
    assert res.json()["updated"] == 2 and res.json()["rooms"] == 2
    assert _outbox(app)[-1].new_ver == 2


def test_import_dry_run_changes_nothing(client, app, seeded):
    r1, _ = seeded
    res = _post(client, HEADER + "명지,E,301,금,09:00,10:00,수업,새로,\n", dry_run="true")
    assert res.status_code == 200 and res.json()["added"] == 1 and res.json()["outbox_ids"] == []
    assert len(_slots(app, r1)) == 2 and _outbox(app) == []


def test_import_rejects_non_utf8_and_too_large(client, seeded):
    res = client.post("/api/import/slots", content=(HEADER + "명지,E,301,월,09:00,10:00,1,a,\n").encode("cp949"),
                      headers={"content-type": "text/csv"})
    assert res.status_code == 400 and "UTF-8" in res.json()["detail"]
    res = client.post("/api/import/slots", content=b"x" * (1024 * 1024 + 1), headers={"content-type": "text/csv"})
    assert res.status_code == 413


def test_import_enqueue_failure_after_commit_returns_500_with_hint(client, app, seeded, monkeypatch):
    from app.lora_service import api

    def boom(*a, **k):
        raise RuntimeError("hub down")

    monkeypatch.setattr(api, "enqueue_file_replace", boom)
    r1, _ = seeded
    res = _post(client, HEADER + "명지,E,301,금,09:00,10:00,수업,새로,\n")
    assert res.status_code == 500 and "sync" in res.json()["detail"]
    assert len(_slots(app, r1)) == 3  # DB 는 반영됨
```

`test_import_rejects_non_utf8_and_too_large`: `"명지"`를 cp949로 인코딩한 바이트는 UTF-8로 디코드되지 않는다(`\xb8\xed`). 만약 우연히 디코드되면 `"학교"`처럼 다른 글자로 바꾼다.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_csv_import.py -k import_ -q`
Expected: FAIL `assert 404 == 400` 등

- [ ] **Step 3: 스키마**

`server/app/schemas.py` `Enqueued` 아래:

```python
class ImportSkipped(BaseModel):
    row: int
    reason: str


class ImportSummary(BaseModel):
    rooms: int
    added: int
    updated: int
    deleted: int
    skipped: list[ImportSkipped]
    outbox_ids: list[int]


class ImportRowError(BaseModel):
    row: int
    error: str


class ImportErrors(BaseModel):
    errors: list[ImportRowError]
```

- [ ] **Step 4: 라우터**

`server/app/domain/router.py` — import에 `from dataclasses import asdict`, `from fastapi.responses import JSONResponse`, `from app.domain import csv_import`. `sync_room` 아래:

```python
IMPORT_MAX_BYTES = 1024 * 1024


@router.post(
    "/import/slots",
    response_model=S.ImportSummary,
    responses={400: {"model": S.ImportErrors}, 413: {}, 500: {}},
)
async def import_slots(request: Request, dry_run: bool = False, s: Session = _DB):
    """시간표 CSV (S2b §4). 본문 = CSV 텍스트(text/csv). 전체 검증 → 적용 → commit → 방마다 콘텐츠 FILE."""
    raw = await request.body()
    if len(raw) > IMPORT_MAX_BYTES:
        raise HTTPException(413, f"{IMPORT_MAX_BYTES} B 초과")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise HTTPException(400, "UTF-8 로 저장하세요 (엑셀: CSV UTF-8)") from e
    rows, errors = csv_import.parse(text, s)
    if errors:
        return JSONResponse(status_code=400, content={"errors": [asdict(e) for e in errors]})
    sm = csv_import.apply(rows, s, dry_run=dry_run)
    if dry_run:
        return {**asdict(sm), "outbox_ids": []}
    s.commit()  # RecordProvider 가 커밋된 슬롯을 읽어야 FILE 내용이 새 것이다 (S2b §3)
    ids: list[int] = []
    try:
        for bld, room in sm.changed:
            ids += api.enqueue_file_replace(bld, room, "schedule")
    except Exception as e:  # DB 는 이미 반영됨 — 관리자가 sync 로 복구
        raise HTTPException(
            500, f"FILE 큐잉 실패 ({e}). DB 는 반영됨 — POST /api/rooms/{{id}}/sync 로 재전송"
        ) from e
    return {**asdict(sm), "outbox_ids": ids}
```

`JSONResponse`는 `from fastapi.responses import JSONResponse`. `asdict(sm)`에는 `changed`가 들어가는데 `response_model`이 걸러낸다 — 그래도 명시적으로 `{k: v for k, v in asdict(sm).items() if k != "changed"}`가 읽기 낫다면 그렇게. 라우터 함수가 `async`인 이유는 `request.body()`뿐이다 — 도메인 세션(`_DB`)은 동기 의존성이라 그대로 쓸 수 있다. `s.commit()` 뒤 `get_db`의 `s.begin()` 컨텍스트가 끝날 때 다시 커밋을 시도하는데, 이미 커밋된 세션에서 `begin()` 종료는 no-op이다 — `test_room_change_resends_config_after_commit`(기존)이 같은 패턴.

- [ ] **Step 5: 정적 폼**

`server/static/index.html` 시간표 폼 아래:

```html
<h2>시간표 CSV 임포트</h2>
<form id="csv">
  <input type="file" name="file" accept=".csv,text/csv">
  <button name="mode" value="dry">미리보기</button>
  <button name="mode" value="apply">적용</button>
</form>
<pre id="csv_out"></pre>
```

script에:

```js
document.querySelector('#csv').onsubmit = async e => {
  e.preventDefault();
  const file = e.target.file.files[0];
  if (!file) return;
  const dry = e.submitter.value === 'dry';
  const r = await fetch(`/api/import/slots?dry_run=${dry}`, {method: 'POST', headers: {'content-type': 'text/csv'}, body: file});
  document.querySelector('#csv_out').textContent = r.status + ' ' + JSON.stringify(await r.json(), null, 1);
  refresh();
};
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest -q` → 전부 PASS. ruff. `uv run uvicorn --factory app.main:create_app --port 8000`으로 띄워 `/static/index.html`에서 CSV 파일 미리보기·적용이 되는지 손으로 한 번(스모크, 선택).

- [ ] **Step 7: 커밋**

```bash
git add app/schemas.py app/domain/router.py static/index.html tests/test_csv_import.py
git commit -m "feat(server): POST /api/import/slots — CSV 전체 검증·적용·commit 후 콘텐츠 FILE, dry_run, 정적 폼"
```

---

### Task 6: 문서·진행도

**Files:**
- Modify: `server/README.md`
- Modify: `docs/progress.html` (wj-04 체크)
- Modify: `docs/specs/2026-09-14-s2-server-design.md` (§1 비목표 "CSV 임포트" → S2b 링크 한 줄)

- [ ] **Step 1: README**

`server/README.md` "모뎀Pi 등록" 줄 아래:

```markdown
- 시간표 CSV: `POST /api/import/slots` 본문에 CSV 텍스트(`text/csv`, UTF-8). 규격·출처 규칙은 `../docs/specs/2026-09-16-s2b-csv-import-design.md` §2. `?dry_run=true`로 미리보기.
```

- [ ] **Step 2: 진행도**

`docs/progress.html` `id="wj-04"` 체크박스에 ` checked data-done="<오늘 날짜>"`, PR란은 비워 둔다(PR 번호는 PR 생성 후).

- [ ] **Step 3: S2 spec 비목표 한 줄**

`docs/specs/2026-09-14-s2-server-design.md` §1 비목표의 "CSV 임포트, 학생 웹 API, …" 줄 끝에 ` (CSV 임포트는 2026-09-16 S2b spec으로 구현)`.

- [ ] **Step 4: 커밋**

```bash
git add server/README.md docs/progress.html docs/specs/2026-09-14-s2-server-design.md
git commit -m "docs: CSV 임포트 README·진행도(wj-04)·S2 spec 비목표 링크"
```

(이 커밋은 저장소 루트에서.)

---

## Self-review

- **Spec coverage:** §2.1 규격 → Task 3. §2.2 출처·PUT 409·마이그레이션 → Task 1. §2.3 적용 → Task 4. §2.4 `enqueue_file_replace` → Task 2. §3 순서·413·UTF-8·enqueue 실패 500 → Task 5. §4 엔드포인트·응답·정적 폼 → Task 5. §5 로드맵 계약 ⑤ 링크 → cw 문서라 PR 본문에 요청(Task 없음, 의도). §6 테스트 목록 → Task 1~5. §8 성공 기준 "60행 → FILE 레코드 60개"는 Task 5 테스트가 3행으로 축소해 같은 경로를 검증.
- **Placeholder scan:** `<rev>`는 alembic이 생성하는 값(의도). 그 외 없음.
- **Type consistency:** `Row`/`RowError`/`Summary`/`parse`/`apply` 시그니처 Task 3·4·5 일치. `enqueue_file_replace(bld, room, kind, unit=0)` Task 2·5 일치. `Summary.changed: list[tuple[str, int]]`를 Task 5가 `for bld, room in sm.changed`로 소비.
