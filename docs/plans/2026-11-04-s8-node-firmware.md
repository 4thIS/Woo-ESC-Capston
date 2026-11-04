# S8 노드 펌웨어(깨어 있는 모드) — 구현 계획 (plan)

- 생성일시: 2026-11-04
- 기준 spec: `docs/specs/2026-09-09-lora-v2-wor-design.md` §3.4·3.5(ACK·TXN)·§5.1~5.3(저장·시계·상태 판단)·§6.4·6.6·6.8(수신·대상·업링크), 로드맵 cw-14

**Goal:** ESP노드 정식 펌웨어 `[env:terminal]` — 깨어 있는 모드로 수신·대상 필터·DUP/GAP·전 TYPE 적용·저장 후 ACK → 렌더.

**범위 (2026-11-04 결정 — "시연에 문제없는 수준"):**
- 넣는다: TIME·SLOT_SET/DEL·DAY_CLEAR·RESV_SET/DEL·EXAM_SET/DEL·FILE(3 kind) 적용, `ACK_REQ` 일 때만 ACK(브로드캐스트는 응답 없음), ACK 전 CAD 1회(§6.8), 상태를 LittleFS 에 저장(재부팅해도 시간표 유지), 판정 §5.3(벡터 통과), 패널 리프레시 중 수신·ACK(busy 콜백, 10/28 실기 교훈), 시계 무효면 그리지 않음.
- 넣지 않는다(S9): 딥슬립·WOR(cw-16), 프로비저닝 SET_ROOM·HELLO·STATUS·버튼(cw-17), 배터리 측정. 정체성은 빌드 플래그 `NODE_BLD/ROOM/UNIT`.
- **임시 구현**: 상태 판단(`nc::decide`)과 저장 형식(`nc::State` 통째 저장)은 dh-08(`lib/schedule`·`lib/node_store`, #74)이 들어오면 바꿔 끼운다. 판정은 `lora_proto/room_state_vectors.json` 으로 검증하므로 교체 후에도 같은 벡터를 통과해야 한다.

**Architecture:**
- `lib/node_core/` — 하드웨어 없는 순수 로직(native 테스트). `handleFrame`(§6.4 dispatch, DUP·GAP `mod 255`·`lastTxn` 은 OK/GAP 일 때만 — #74 10), `isForMe`(§6.6), `decide`(§5.3 판정 + `until`), `toKst`(epoch + 9 h, §5.2), `buildModel`(→ RenderModel, 쉬는시간이면 cur = next — #89).
- `src/terminal/main.cpp` — SX1262(DIO1 인터럽트)·LittleFS(`/state.bin`, tmp → rename 원자 교체, 손상 시 비움 → 서버 GAP 재동기)·GxEPD2 + `renderLayout`. 저장 실패면 적용을 되돌리고 `STORE_FAIL`.
- 출발점은 10/28 실기 E2E 의 `firmware/bringup/e2e/src/node/main.cpp`(미커밋). 차이: 주간 96 슬롯·FILE 8 KB(시연판 48·2 KB), `ACK_REQ` 규칙(시연판은 TIME 만 무응답), LittleFS 영속, 판정을 벡터 기준으로.

**Tech Stack:** PlatformIO / C++17, Arduino-ESP32(espressif32@7.0.1), RadioLib 7.1.2, GxEPD2 1.6.2, Unity(native)

---

### Task 1: `lib/node_core` + 테스트 (`test/test_node_core`, 20개)
- 대상 필터, GAP `mod 255`, SLOT_SET OK → GAP → DUP, 같은 키 교체, 가득 차면 STORE_FAIL·`lastTxn` 유지, SLOT_DEL·DAY_CLEAR, RESV·EXAM, TIME(브로드캐스트 무응답·대상 TIME 은 DUP 아님), `ACK_REQ` 없으면 무응답, BAD_PAYLOAD·UNSUPPORTED, FILE 전체 교체·FILE_MISSING(첫 누락 seq)·BAD_CRC
- `room_state_vectors.json` 25개(layout·until), KST 변환, RenderModel(수업·쉬는시간 cur = next·예약 우선·시험기간)

### Task 2: `[env:terminal]` + `src/terminal/main.cpp`
- `pio run -e terminal` 성공, 폰트·이미지 임베드(`extra_scripts`)

### Task 3: 실기 확인 + PR
- 노드에 굽고, 관리자 웹 변경 → 모뎀Pi → 노드 `acked`·화면 전환, 재부팅 후 상태 유지(LittleFS), 버전 0 노드에 GAP → FILE 재동기
- 게이트: `pio test -e native`(node_core·modem_core·codec), `pio run -e terminal`·`-e modem`, `pio check`
