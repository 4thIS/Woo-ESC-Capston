# firmware — 영역 가이드

> 루트 `../CLAUDE.md`를 먼저 읽으십시오. 이 파일은 firmware 영역 특수 규칙만 다룹니다.
> 구현 근거는 `../docs/specs/2026-09-09-lora-v2-wor-design.md` §4(모뎀)·§5~7(단말)입니다.

## 스택

- 언어/런타임: C++17 / Arduino-ESP32 (ESP32-S3, Heltec WiFi LoRa 32 V3 + SX1262)
- 패키지 매니저: **PlatformIO (`pio`)** (다른 매니저 사용 금지 — 라이브러리는 `platformio.ini`의 `lib_deps`로만 추가)
- 테스트: Unity (`pio test -e native` — 호스트에서 도는 로직 테스트)
- 린트·포맷: `pio check` (cppcheck) + `clang-format`
- 주요 라이브러리: RadioLib(SX1262), GxEPD2(e-Paper), ArduinoJson(모뎀 전용)

## 폴더 규칙

```
firmware/
├── lib/lora_codec/   # 프레임 인코딩/디코딩 — 단말·모뎀 공용 (보호 계층)
├── src/terminal/     # 단말 펌웨어: 상태머신·절전·수신·저장·렌더 (스펙 §5~7)
├── src/modem/        # 게이트웨이 모뎀 펌웨어: USB 시리얼 JSON lines (스펙 §4)
├── src/fonts/        # 폰트·이미지 리소스 (v1에서 이식)
└── test/             # Unity: codec, determineLayout, nextChangeAt
```

- 빌드 env는 `[env:terminal]`, `[env:modem]`, 테스트용 `[env:native]` 세 개다. env를 늘리기 전에 PM과 협의한다.

## 계층 책임

- `lib/lora_codec/`는 **순수 로직만** 담는다 — 라디오 드라이버·Serial·파일시스템을 import하지 않는다. 그래야 `native` env에서 테스트 벡터로 검증된다.
- `src/terminal/`의 상태 판단(`determineLayout`)과 다음 변경 시각(`nextChangeAt`)도 하드웨어 의존 없이 순수 함수로 유지한다 — 경계값 테스트가 여기 걸린다.
- 렌더 계층(`render*`, `fonts/`)은 데이터를 해석하지 않는다. 무엇을 보여줄지는 상태 판단이 정하고, 렌더는 그대로 그리기만 한다.
- 공통 인프라 계층은 도메인을 import하지 않는다(의존 방향 단방향 유지).

## 영역 내 소유권 분할

| 경로 | 담당 |
|------|------|
| `lib/lora_codec/`, `src/modem/`, `src/terminal/` (무선·절전·스케줄링·저장) | cw @ssenu |
| `src/terminal/render*`, `src/terminal/display*`, `src/fonts/` | dh @Hyeon02-kr |

두 담당이 같은 영역을 쓰므로, **상태 판단 ↔ 렌더 사이의 인터페이스**(레이아웃 구조체·그리기 함수 시그니처)가 이 영역의 내부 계약이다. 바꾸려면 상대와 사전 협의한다.

## 커밋 scope

- `feat(firmware):`, `fix(firmware):`, `style(firmware):`

## 테스트

- 새 코드는 테스트 동반(TDD: 실패 → 구현 → 통과).
- codec은 `lora_proto/test_vectors.json`을 읽어 **Python이 만든 프레임과 바이트 단위로 일치**함을 확인한다. 벡터 없이 통과하는 codec 테스트는 무의미하다.
- 하드웨어 의존 동작(라디오 수신률·딥슬립 전류)은 유닛 테스트 대상이 아니다 — 스펙 §10.2 벤치 절차로 실측하고 결과를 PR에 첨부한다.

## 계약(Contract) 규칙

- 이 영역은 `lora_proto/`의 **소비자**다. 상수·프레임 오프셋을 여기서 재정의하거나 로컬 상수로 복사하지 않는다 — 계약이 두 곳에 생겨 어긋난다.
- 프레임 규격을 바꿔야 하면 `lora_proto/`를 PM이 먼저 고쳐 머지하고(lockstep), 그다음 이 영역이 따라간다.

## 절대 하지 말 것

- 다른 영역 디렉토리(`server/`, `web/`) 수정 금지 — 필요 시 이슈로 요청.
- `lora_proto/` 직접 수정 금지 (PM 전담).
- `platformio.ini`의 보드·프레임워크·언어 표준 임의 변경 금지.
- 프레임 규격 변경 시 서버 담당과 사전 협의 + PR에 BREAKING CHANGE 명시.
- 계층 규율 경로(`lib/lora_codec/`)를 기준 대조 없이 수정 금지.
