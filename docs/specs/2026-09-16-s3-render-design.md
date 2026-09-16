# S3 — 렌더 계층 이식 + 호스트 PNG 프리뷰 설계 (spec)

- 생성일시: 2026-09-16
- 수정일시: 2026-09-16
- 상위 문서: `2026-09-09-lora-v2-wor-design.md` §5.3(레이아웃 표)·§6.9(렌더링 자산). `2026-09-09-roadmap-design.md` §4.1(RenderModel)·§5(S3)·§6.1(가짜 하드웨어 셋)·§6.3(렌더 프리뷰)·§10(하루 최대 교시 — 이 문서가 확정).
- 담당: dh @Hyeon02-kr. 영역 `firmware/src/terminal/render*`·`firmware/src/fonts/`·`firmware/tools/`(프리뷰 도구). 상대: 노드 상태 판단(cw, `firmware/src/terminal/` 비-render 부분)과는 `render_model.h`로만 만난다.

## 0. 배경 · 위치

로드맵 §2(접근법 B)의 "하드웨어 없는 3주" 산출물 중 렌더 프리뷰(§6.3)를 만든다. 부품이 5주차에나 도착하므로, 그 전에 mh·wj가 레이아웃을 리뷰(dh-04, 4주차 완료 기준)하려면 호스트에서 **실기와 동일한 코드**로 PNG를 뽑아야 한다.

v1(`esp32_e-paper_syllabus`, 상위 폴더에서 실물 확인)은 실제 GxEPD2(`GxEPD2_3C<GxEPD2_750c_Z08, ...>`)를 쓰고 `firstPage()/nextPage()` 페이지 루프로 그린다 — 이식 가능. 다만 v1의 `renderLayout()`은 `prev`/`cur`/`next`/`nextNext` **4슬롯만** 그리고, 로드맵 §4.1 RenderModel의 `today[]`(오늘 전체 목록) 패널에 대응하는 코드가 **v1에 없다**. 이 부분은 "이식"이 아니라 신규 설계다(§9에 조사 근거).

같은 상위 폴더의 `e-fairboard-project`도 확인했으나 다른 하드웨어(12.48" Waveshare HAT, GxEPD2 미사용, 자체 `ICanvas` 추상화)라 직접 참고 대상이 아니다(§9).

## 1. 목표 · 비목표

### 목표
- 그리기 인터페이스: **Adafruit_GFX 기반 클래스 계층을 실기·호스트가 그대로 공유**한다. 렌더 함수는 `Adafruit_GFX&`(또는 그 파생 타입) 하나만 받고, GxEPD2 실기 클래스와 호스트 프레임버퍼 클래스가 각각 그 타입을 만족한다.
- `RenderModel.today[12]` → **`today[24]`** 로 변경 제안 (근거: §2.1).
- 픽스처 JSON 형식을 S1의 관례(JSON은 snake_case, C++ 구조체는 camelCase, `lora_proto/test_vectors.json` 패턴)를 그대로 따라 확정한다.
- 레이아웃 1~8은 새로 정의하지 않고 v2 §5.3 표를 참조하며, `today[]` 패널이 v1에 없는 신규 UI임을 명시한다.
- `firmware/tools/host_gfx.{h,cpp}` (호스트 프레임버퍼) + `render_preview.cpp`(네이티브 실행파일) + `render_preview.py`(오케스트레이션)를 설계한다.

### 비목표 (이번엔 안 함 / 후속)
- 8개 레이아웃의 실제 픽셀 배치 확정 (→ dh-04, v1 이식 + `today[]` 신규 설계)
- 경계 케이스 픽스처 15개 작성 (→ dh-05)
- 실물 패널 연결 (→ dh-06)
- `determineLayout`의 야간 교시 판정 로직 수정 (→ cw, 이슈로 요청. §5)

## 2. 데이터 · 계약

- `RenderModel` 변경: **예** (`today[12]` → `today[24]`). `lora_proto/` 계약이 아니라 firmware 내부의 cw↔dh 계약(로드맵 §4.1)이라 lockstep PR 규칙 대상은 아니지만, 이 spec의 제안은 **초안**이며 최종 동결은 로드맵 일정대로 4주차 `cw-11`(계약 7개 동결 리뷰)에서 확정된다.
- `lora_proto/` 변경: 아니오
- DB 스키마·응답 스키마 변경: 아니오

### 2.1 `today[24]` 산정 근거

**출처**: 명지전문대학 수강신청시스템(sugang.mjc.ac.kr) 교시확인표.

| 구분 | 교시 수 | 시간대 |
|---|---|---|
| 주간 (0.5~9.0, 0.5 단위, 25분 블록) | 18 | 09:00~17:50 |
| 야간 (1.0~6.0, 1.0 단위, 45분 수업+5분 휴식) | 6 | 18:00~22:55 |
| **합계** | **24** | 09:00~22:55 |

**주간 0.5 단위는 9개(0.5+1.0을 50분 블록으로 병합)로 줄일 수 없다.** 0.5교시(예: 5.0=13:25-13:50)와 다음 0.5교시(5.5=14:00-14:25) 사이에 10분 휴식이 끼어 있어도, 실제 개설 과목은 이 경계와 무관하게 독립적으로 시작·종료한다 — 예: 1학년 통합전공교과 "딥러닝" 101반은 화요일 **13:25~14:50**(5.0·5.5·6.0에 걸침, 중간 10분 휴식 포함), 수요일 **10:25~11:50**(2.0·2.5·3.0에 걸침)로 개설되어 있다. 병합하면 이런 과목의 시작·종료 시각을 `today[]`에 표현할 수 없으므로 18개 전부를 독립 슬롯으로 유지한다.

한 강의실이 하루에 가질 수 있는 서로 다른 시작 시각(=최악의 경우 서로 다른 과목이 들어갈 수 있는 슬롯 수)의 최댓값이 24이므로, `today[]`는 이 수를 손실 없이 담아야 한다. `RenderModel`은 로드맵 §4.1에 "≈ 550 B, **매 웨이크 재계산**"이라 명시된 임시 구조체로(2026-09-16 QR·battPct 제거 후 갱신된 값) `rtc_state_t`(RTC slow memory 8 KB 제한)에 영속 저장되지 않으므로, 24로 늘려도(약 +312 B) ESP32-S3 SRAM(512 KB)에 실질적 제약이 없다.

```c
struct { uint8_t sH,sM,eH,eM; char subj[21]; uint8_t type; } today[24];  // 09:00~22:55, 주간 18 + 야간 6
```

## 3. 접근 제어 / 제약

- 렌더 함수(`renderLayout` 등)는 `Adafruit_GFX&` 타입에만 의존한다. 실기 초기화(`display.init()`)·전원 관리(`hibernate()`, `epd2.powerOff()`)는 렌더 함수 밖, 호출자(S8 상태머신) 책임이다. 호스트 쪽은 이 호출들을 이름만 맞춘 no-op으로 스텁한다.
- 문자열 길이는 `lora_proto.proto.SUBJ_MAX`(20 B)·`PROF_MAX`(12 B) 그대로 — 렌더 계층은 잘라내지 않는다(상위 계층이 이미 보장, v2 §5.1).
- 픽스처 JSON 키는 snake_case, C++ `RenderModel` 필드는 camelCase (S1 관례, §4.2).
- PNG 출력은 800×480, 3색(흰/검/빨강)을 그대로 RGB 값으로 매핑해 저장한다(디더링 없음 — 실기와 동일하게 3색만 존재).

## 4. 인터페이스 계약

### 4.1 파일 구조 (신규)

```
firmware/
├── src/terminal/
│   ├── render.h / render.cpp        # renderLayout() 등 — Adafruit_GFX& 인자 (실기·호스트 공용, dh)
│   └── render_model.h               # RenderModel 구조체 (cw·dh 공용 내부 계약)
├── tools/
│   ├── host_gfx.h / host_gfx.cpp    # Adafruit_GFX 파생, drawPixel()만 구현하는 800×480×3색 프레임버퍼
│   ├── render_preview.cpp           # argv[1]=픽스처 JSON 경로 → RenderModel 파싱(ArduinoJson) → renderLayout() → PNG 저장
│   └── render_preview.py            # 위 실행파일을 firmware/test/fixtures/render/*.json 전체에 일괄 호출
└── test/fixtures/render/*.json      # 픽스처 (로드맵 §6.3에 경로 명시됨)
```

### 4.2 `RenderModel` 전체 정의 (로드맵 §4.1 확정 + §2.1 변경분)

```c
typedef struct {
  uint8_t  layout;              // v2 §5.3 표의 1~8
  char     bld; uint16_t room; uint8_t unit;
  char     nowStr[6];           // "HH:MM"
  uint8_t  weekday;             // 1=월..7=일
  struct { char subj[21]; char prof[13];
           uint8_t sH,sM,eH,eM; uint8_t type; uint8_t flags; } prev, cur, next;
  uint8_t  nToday;
  struct { uint8_t sH,sM,eH,eM; char subj[21]; uint8_t type; } today[24];  // §2.1
  uint16_t battMv;
} RenderModel;
```

`qrUrl`·`battPct` 없음 — 2026-09-16 팀 결정(QR 미사용, PR #15)으로 로드맵 r4에서 제거. 이 spec 최초 작성 시점의 초안에는 있었으나 로드맵 §4.1이 원본이라 그쪽을 따른다.

### 4.3 그리기 인터페이스

```c
// firmware/src/terminal/render.h
void renderLayout(Adafruit_GFX& gfx, const RenderModel& model);
```

- 실기: `GxEPD2_3C<GxEPD2_750c_Z08, ...> display(...)` — `Adafruit_GFX`를 상속하므로 그대로 전달.
- 호스트: `HostGfx : public Adafruit_GFX` — `drawPixel(int16_t x, int16_t y, uint16_t color)` 하나만 오버라이드. `fillRect`/`print`/`drawBitmap`/폰트 렌더링은 Adafruit_GFX 원본 코드가 그대로 수행하므로 호스트·실기가 바이트 단위로 동일하게 그린다.

### 4.4 픽스처 JSON 스키마 (S1 관례 — snake_case)

```json
{
  "name": "layout1_class_basic",
  "layout": 1, "bld": "E", "room": 301, "unit": 1,
  "now_str": "09:30", "weekday": 3,
  "prev": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "cur":  {"subj": "자료구조", "prof": "김교수", "s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "type": 1, "flags": 1},
  "next": {"subj": "", "prof": "", "s_h": 0, "s_m": 0, "e_h": 0, "e_m": 0, "type": 0, "flags": 0},
  "n_today": 3,
  "today": [
    {"s_h": 9, "s_m": 0, "e_h": 9, "e_m": 50, "subj": "자료구조", "type": 1}
  ],
  "batt_mv": 3900
}
```

`render_preview.cpp`는 ArduinoJson으로 이 JSON을 읽어 `RenderModel`(camelCase 필드)을 채운다 — 매핑 규칙은 `lora_proto/test_vectors.json` ↔ `lora_codec.h`가 이미 쓰는 것과 동일(`s_h`→`sH` 등).

## 5. 영역별 영향

- firmware: 이 문서 전부(dh 작성).
- **cw 확인 필요 (작성자 아님)**: `firmware/platformio.ini`는 S1에서 cw가 만든 파일이다. `render_preview.cpp`를 `[env:native]`에서 `pio run -e native`(일반 프로그램 빌드 경로, `pio test -e native`와는 별개)로 돌리려면 `src_filter` 설정 추가가 필요하다. 새 env를 만드는 건 아니라 firmware/CLAUDE.md의 "env 늘리기 전 PM 협의" 규칙 대상은 아니지만, 공용 파일이라 PR에서 cw 확인을 받는다(§9).
- **cw에게 이슈로 전달**: `determineLayout`(v2 §5.3, cw 소유)의 "분 < 50 → 수업중 / 분 ≥ 50 → 쉬는시간" 판정은 주간(매시 :00~:50 정렬)에는 맞지만, §2.1의 야간 교시(18:00-18:45, 18:50-19:35 — 45분 수업 + 5분 휴식, 시각 정렬이 다름)에는 맞지 않는다. 렌더 계층이 아니라 상태 판단 로직이라 여기서 고치지 않고 이슈로 남긴다.
- 그 외 영역(server/modempi/web): 영향 없음.

## 6. 무회귀 · 롤아웃

- 기존 렌더 코드가 이 리포에 없으므로(v1은 별도 레포) 회귀 대상 없음.
- `RenderModel.today[24]` 변경은 이 spec에서 제안하는 초안이며, 로드맵 일정상 4주차 `cw-11`에서 cw와 함께 최종 동결한다. 그 전까지 dh-03·dh-04(3주차)는 이 spec을 기준으로 먼저 진행해도 무방하다(로드맵 §6.4).
- `platformio.ini` 변경은 이 spec에 설계만 남기고, 실제 PR에서 cw 리뷰를 받은 뒤 반영한다.

## 7. 역할 분담

| 영역 | 담당 |
|------|------|
| `firmware/src/terminal/render*`, `firmware/src/fonts/`, `firmware/tools/` | dh @Hyeon02-kr |
| `render_model.h` 필드 최종 동결 | dh 제안 → cw @ssenu 확인 (4주차 `cw-11`) |
| `platformio.ini` native env 설정 검토 | cw @ssenu |
| `determineLayout` 야간 교시 판정 수정 | cw @ssenu (이슈로 별도 요청) |

## 8. 성공 기준

- `pio test -e native`가 계속 녹색으로 통과한다(기존 S1 codec 테스트에 영향 없음).
- `render_preview.py`가 `firmware/test/fixtures/render/*.json` 각각에 대해 PNG 1장씩 생성한다.
- 레이아웃 1~8용 픽스처 최소 8개는 이 spec의 포맷을 따르되 실제 작성은 dh-04에서.
- 이 문서가 `docs/specs/`에 PR로 올라가고 cw가 §5·§9의 확인 항목(RenderModel 변경, platformio.ini, determineLayout 이슈)을 리뷰한다.

## 9. 열린 결정 (plan 단계에서 확정)

- `platformio.ini`의 `[env:native]` `src_filter` 정확한 구성 — cw 확인 후 확정.
- PNG 저장 라이브러리 — 헤더 온리 `stb_image_write.h`를 제안(단일 파일, 별도 의존성 관리 불필요). 실제 도입 시 라이선스 재확인 필요.
- `today[]` 패널의 실제 화면 배치(위치·폰트 크기)는 v1에 대응 코드가 없어 dh-04에서 신규 설계.
- **v1(`esp32_e-paper_syllabus`) 조사 결과** (상위 폴더 실물 확인): `GxEPD2_3C<GxEPD2_750c_Z08, HEIGHT/2>` 사용, `firstPage()/nextPage()` 페이지 드로잉(페이지 높이 = 전체의 절반 — ESP32 RAM 제약, ESP32-S3는 전체 버퍼도 가능). `renderLayout()`은 prev/cur/next/nextNext 4슬롯만 그리며 `today[]` 목록 렌더는 없음.
- **`e-fairboard-project` 조사 결과**: 다른 하드웨어(12.48" Waveshare HAT, `EPD_12in48b` 원시 드라이버, GxEPD2 미사용)라 직접 참고 대상 아님. 자체 `ICanvas`/`IGlyphSource` 커스텀 추상화 전례가 있으나, GxEPD2가 아예 없어서 선택한 것이라 이 프로젝트의 A안 결정과는 무관. "오늘 목록" 류 개념도 없음(게시판 성격의 다른 제품).
