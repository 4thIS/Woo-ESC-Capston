# 강의실 e-Paper 시스템 v2 — LoRa 송수신·절전 단말·게이트웨이 설계 스펙

> 작성일: 2026-09-09
> 상태: 설계 확정(구현 전). 별도 레포에서 이 문서만 보고 구현할 수 있도록 작성.
> 범위: **단말 펌웨어 · 게이트웨이(모뎀) 펌웨어 · 백엔드 LoRa 서비스 계층 · 공중/시리얼 프로토콜**.
> 비범위: 관리자/학생 웹 UI, 로그인, 예약 비즈니스 로직 (별도 세션). 웹은 §8의 `outbox` / `terminal_status` 계약만 사용한다.
>
> **개정 (2026-09-09 r2)**: 팀 협의로 메인Pi(웹서버 1) → 모뎀Pi(건물당 1) → ESP노드 3계층 토폴로지가 확정되었다. **§8(백엔드 LoRa 서비스)은 `2026-09-09-roadmap-design.md` §3·§4로 대체된다** — §8.4 워커·`modem.py`·`codec.py`는 모뎀Pi(`modempi/lora/`)로, outbox·버전·`api.py`는 메인Pi에 남되 WS 허브가 추가된다. §2~§7(무선·프레임·모뎀 펌웨어·노드 펌웨어)은 그대로 유효하다. 용어: "단말" = ESP노드, "게이트웨이" = 모뎀Pi.

---

## 0. 한 장 요약

| 항목 | v1 (현재 레포) | v2 (이 스펙) |
|---|---|---|
| 단말 | Waveshare ESP32 Driver Board + EBYTE UART HAT | **Heltec WiFi LoRa 32 V3** (ESP32-S3 + SX1262 SPI) + DESPI-C02 어댑터 + 기존 7.5" 3색 패널 |
| 게이트웨이 | PC/Pi COM 포트에 EBYTE UART HAT | **Heltec V3 한 장을 USB 시리얼 "모뎀"으로** (JSON lines) |
| 주파수 | 868 MHz (EU) | **922.5 MHz (KR920, 917~923.5 MHz 비면허)** + CAD(LBT) |
| 단일 패킷 | 29 B (HAT 한계) | **≤ 255 B** (SX1262 직접 제어) → 청크 인프라 폐지, 프레임 = 의미 1개 |
| 단말 전력 | 상시 깨어 있음(≈50 mA) | **딥슬립 + SX1262 Rx Duty Cycle + DIO1 웨이크** (목표 ≤ 15 mAh/일) |
| 상태 판단 | 단말 자율 (`determineLayout`) | **그대로 유지**. 서버는 데이터·시각만 준다 |
| 신뢰성 | CRC8 + ACK + 멱등 | + **버전 벡터**(패치 유실 즉시 감지·자가 재동기) + **일 1회 STATUS 업링크** |
| 초기설정 | BLE + HTTPS 폰 페이지 | **LoRa 프로비저닝**(HELLO/SET_ROOM). BLE 제거 |
| 배터리 | 없음(USB) | DTP105085 3.7 V 5,000 mAh LiPo, Vext 게이팅 |

**설계 원칙**
1. 백엔드는 "무엇을 보낼지", 모뎀은 "언제·어떻게 쏠지", 단말은 "지금 뭘 보여줄지"만 안다.
2. 모든 상태 변경은 **멱등**이고 **버전이 붙는다**. 유실은 재전송이 아니라 재동기로 흡수한다.
3. 단말은 서버가 죽어도 자기 시계·자기 데이터로 계속 옳은 화면을 보여준다(fail-operational).
4. 상수는 한 곳(`lora_proto/`)에서만 정의하고 Python·C++가 같은 테스트 벡터로 검증된다.

---

## 1. 하드웨어

### 1.1 BOM (단말 1대)

| 부품 | 모델 | 비고 |
|---|---|---|
| MCU + LoRa | Heltec WiFi LoRa 32 V3 (ESP32-S3FN8 + SX1262, 863~928 MHz) | devicemart no=14894560 |
| e-Paper 패널 | Waveshare 7.5" (B) 800×480 흑/백/적, UC8179, 24핀 FPC (기존 보유) 또는 Goodisplay GDEY075Z08 | no=15331635 |
| 패널 어댑터 | Goodisplay DESPI-C02 (24핀 SPI, 수동 보드, 3.3 V) | no=15331593 |
| 배터리 | Mini Battery DTP105085 3.7 V 5,000 mAh, Molex 51021 1.25 mm 2핀, KC | no=15285796. **PCM 내장 여부 스펙시트 확인, 커넥터 극성 확인 필수** |
| 안테나 | Heltec U.FL 스틱 3 dBi 915 MHz | no=14898693 |
| 버튼 | 보드 내장 PRG 버튼(GPIO0) 사용 | 별도 부품 없음 |

### 1.2 BOM (게이트웨이)

| 부품 | 모델 |
|---|---|
| 모뎀 | Heltec WiFi LoRa 32 V3 (단말과 동일) |
| 피그테일 | Seeed SMA–I-PEX 120 mm (no=14601923) |
| 안테나 | EBYTE TX4G-JKC-19 5 dBi 698~960 MHz SMA (no=15177101) |
| 호스트 | 보유 Raspberry Pi (4 8GB 또는 5 4GB + NVMe). USB-C 케이블로 모뎀 연결 |

### 1.3 Heltec V3 핀 배정 (단말)

| 기능 | GPIO | 비고 |
|---|---|---|
| SX1262 NSS / SCK / MOSI / MISO | 8 / 9 / 10 / 11 | 보드 고정 |
| SX1262 RST / BUSY / **DIO1** | 12 / 13 / **14** | DIO1 = 딥슬립 EXT 웨이크 소스 (RTC GPIO) |
| e-Paper SCK / MOSI / CS / DC / RST / BUSY | 5 / 6 / 7 / 4 / 3 / 2 | FSPI (제2 SPI). 자유 배정 가능하나 이 값을 기본으로 |
| e-Paper 3.3 V | **Vext** | GPIO36 LOW = ON, HIGH = OFF. 슬립 시 OFF |
| 배터리 ADC | GPIO1 (ADC1_CH0), 분압 활성화 GPIO37 LOW | 측정 시에만 GPIO37 LOW, 평소 HIGH(입력 플로팅) |
| 설정/서비스 버튼 | GPIO0 (PRG) | INPUT_PULLUP, 눌림 = LOW, EXT1 웨이크 |
| OLED SDA/SCL/RST | 17 / 18 / 21 | **사용 안 함**. Vext OFF로 전원 차단 |
| LED | 35 | 디버그 빌드에서만 |

게이트웨이는 SX1262 핀만 사용. OLED는 Vext OFF.

### 1.4 전력 설계 목표

| 항목 | 목표 |
|---|---|
| 딥슬립 대기 (ESP + SX1262 duty-cycle + LDO 정지전류) | ≤ 120 µA |
| e-Paper 갱신 1회 (깨어남 + 렌더 + 재슬립) | ≤ 0.25 mAh |
| 일 소모 (갱신 20회 + 동기 24회 + STATUS 1회) | **≤ 15 mAh** |
| 5,000 mAh × 0.85 가용 기준 수명 | **≥ 280일** |

실측 항목(§10.4)으로 검증한다. 목표 미달 시 우선 조치: Vext 차단 확인 → OLED/USB-시리얼 칩 누설 확인 → Rx duty 비율 조정.

---

## 2. 무선 파라미터 (`lora_proto/radio_params.h` 단일 정의)

```c
#define RP_FREQ_MHZ          922.5f     // KR920. 917.0~923.5 내 1채널 고정
#define RP_BW_KHZ            125.0f
#define RP_SF                9          // 실측 후 7~10 조정 (P0)
#define RP_CR                5          // 4/5
#define RP_SYNC_WORD         0x12       // 사설(private). LoRaWAN 0x34와 구분
#define RP_TX_POWER_DBM      14         // 기본 14. 22로 올리기 전 전파법 고시(917~923.5 MHz 출력 상한·LBT) 확인
#define RP_PREAMBLE_NORMAL   8          // 심볼. 깨어 있는 단말·ACK·업링크
#define RP_PREAMBLE_WAKE_MS  3000       // 딥슬립 단말을 깨우는 프리앰블 길이(ms) → 심볼 수는 SF/BW로 환산
#define RP_RX_DUTY_MIN_SYM   8          // Rx duty cycle에서 감지에 필요한 최소 프리앰블 심볼
#define RP_CAD_MAX_TRIES     5          // LBT: CAD busy 시 재시도 횟수
#define RP_CAD_BACKOFF_MIN_MS 50
#define RP_CAD_BACKOFF_MAX_MS 200
#define RP_HW_CRC            1          // SX1262 하드웨어 CRC ON
#define RP_NET_ID            0x4B       // 헤더 netId. 같은 캠퍼스 내 타 실험과 분리
```

- SF9/BW125 기준 심볼 시간 4.096 ms → wake 프리앰블 ≈ 733 심볼. 200 B 페이로드 공중시간 ≈ 1.2 s, wake 포함 ≈ 4.3 s.
- 프리앰블 `wake` 3.0 s 산정 근거: Rx duty 감지 간격(최대 ≈ 1.6 s) + 딥슬립 부팅·라디오 재초기화(≈ 0.5 s) + 여유. 감지가 늦어 본문을 놓친 경우는 §6.5 세션 창 + 백엔드 재시도로 흡수.
- SF 변경 시 `RP_PREAMBLE_WAKE_MS`는 ms 단위라 자동 환산되므로 값 유지.

---

## 3. 공중 프레임 규격 (Air Protocol v2)

### 3.1 공통 헤더 (9 B) + 페이로드 + CRC8

```
offset  size  field
0       1     VER_FLAGS   상위 4비트 = 프로토콜 버전(2), 하위 4비트 플래그
                          bit0 ACK_REQ (1이면 단말이 ACK 송신)
                          bit1 BROADCAST (bld/room/unit 무시)
                          bit2 WAKE_SENT (송신 측이 wake 프리앰블 사용 — 통계용)
1       1     NET_ID      RP_NET_ID 불일치 시 폐기
2       1     TYPE        §3.2
3       1     BLD         ASCII 'E','A','S','M' / 0x00 = 미설정 단말 대상(프로비저닝) / 0xFF = 전체
4..5    2     ROOM        u16 big-endian (1~9999) / 0xFFFF = 전체
6       1     UNIT        1=앞문 2=뒷문 / 0 = 해당 호수 전체 유닛
7       1     TXN         (room,unit) 단위 롤링 1~255. 0은 사용 안 함
8       1     LEN         페이로드 길이 (0~245)
9..     LEN   PAYLOAD
9+LEN   1     CRC8        poly 0x07 init 0x00, offset 0 ~ 9+LEN-1 전체
```
총 길이 ≤ 255 B. 하드웨어 CRC와 별개로 앱 CRC8을 유지한다(하드웨어 CRC 실패 프레임은 칩이 버리므로 앱 CRC는 파서 방어용).

### 3.2 TYPE 목록

| TYPE | 이름 | 방향 | ACK | 프리앰블 |
|---|---|---|---|---|
| 0x01 | TIME | ↓ 브로드캐스트 | 없음 | wake |
| 0x02 | SLOT_SET | ↓ 타겟 | 필수 | wake |
| 0x03 | SLOT_DEL | ↓ 타겟 | 필수 | wake |
| 0x04 | DAY_CLEAR | ↓ 타겟 | 필수 | wake |
| 0x05 | RESV_SET | ↓ 타겟 | 필수 | wake |
| 0x06 | RESV_DEL | ↓ 타겟 | 필수 | wake |
| 0x07 | EXAM_SET | ↓ 타겟 | 필수 | wake |
| 0x08 | EXAM_DEL | ↓ 타겟 | 필수 | wake |
| 0x09 | FILE_BEGIN | ↓ 타겟 | 필수 | wake |
| 0x0A | FILE_DATA | ↓ 타겟 | 필수 | normal (세션 내) |
| 0x0B | FILE_END | ↓ 타겟 | 필수 | normal (세션 내) |
| 0x0C | CMD | ↓ 타겟 | 필수 | wake |
| 0x0D | SET_ROOM | ↓ 프로비저닝 (BLD=0x00) | 필수 | wake |
| 0x10 | ACK | ↑ | — | normal |
| 0x11 | STATUS | ↑ | — | normal |
| 0x12 | HELLO | ↑ (미설정 단말) | — | normal |

### 3.3 페이로드 규격

모든 **변경 다운링크(0x02~0x0B, 0x0D)의 페이로드 첫 바이트는 `NEW_VER`** 다. 해당 kind(시간표/예약/시험기간/정체성)의 새 버전 번호(u8 롤링 1~255, 0=미정)이며, 단말은 적용 후 자기 버전을 이 값으로 갱신한다.

```
TIME        [epoch u32 BE][flags u8]
             flags bit0 REQUEST_STATUS: 수신 단말 전부가 0~300 s 랜덤 지연 후 STATUS 송신

SLOT_SET    [NEW_VER][day u8 1=월..7=일][sH][sM][eH][eM][type u8][subjLen][subj utf8…][profLen][prof utf8…]
SLOT_DEL    [NEW_VER][day][sH][sM]
DAY_CLEAR   [NEW_VER][day]

RESV_SET    [NEW_VER][resvId u16 BE][year-2000 u8][month][day][sH][sM][eH][eM][type u8][subjLen][subj…][profLen][prof…]
RESV_DEL    [NEW_VER][resvId u16 BE]

EXAM_SET    [NEW_VER][examId u16 BE][y1-2000][m1][d1][y2-2000][m2][d2]      (양끝 포함)
EXAM_DEL    [NEW_VER][examId u16 BE]

FILE_BEGIN  [NEW_VER][kind u8 1=schedule 2=resv 3=exam][totalLen u16 BE][nChunks u8]
FILE_DATA   [seq u8 0..nChunks-1][bytes… ≤ 200]
FILE_END    [crc16 u16 BE  (CCITT-FALSE, 파일 전체)]
             파일 본문 = 레코드 반복: [recType u8][recLen u8][recPayload]
             recType = SLOT_SET/RESV_SET/EXAM_SET 와 동일 페이로드(단, NEW_VER 바이트 없음)
             단말은 FILE_END 검증 후 해당 kind를 **전부 비우고** 레코드를 순서대로 적용
             **FILE은 전체 교체이므로 버전 연속성 판정 대상이 아니다.** 단말은 FILE_END 검증 성공 시 자기 버전을 NEW_VER로
             **무조건** 설정하고 OK를 ACK한다. NEW_VER가 이전 값과 같거나 작아도 GAP을 반환하지 않는다.
             (2026-09-14 확정 — 재동기 FILE은 버전을 올리지 않고 현재 버전을 싣기 때문)

CMD         [cmd u8][args…]
             0x01 TEST_RENDER   [layout u8]           지정 레이아웃 즉시 렌더(설치 확인용)
             0x02 REBOOT        —
             0x03 SET_PARAM     [paramId u8][value u32 BE]  (paramId: 1=statusHourUtc 2=sessionWindowMs …)
             0x04 REQUEST_STATUS —
             0x05 FACTORY_RESET —  정체성·데이터 삭제 후 미설정 상태로
             0x06 FORCE_RENDER  —  상태키 무시하고 현재 상태 재렌더

SET_ROOM    [NEW_VER(정체성 버전)][mac 6B][bld u8][roomH][roomL][unit u8]
             헤더 BLD=0x00 ROOM=0 UNIT=0. 미설정 단말만 처리하며 MAC 일치 시 적용

ACK         [status u8][detail u8][batt_mV u16 BE][schedVer][resvVer][examVer][identVer][fw u8][layout u8]
STATUS      ACK 페이로드 + [rssiLast i8][snrLast_x4 i8][flags u8][uptime_h u16 BE]
             flags bit0 CLOCK_STALE(25 h 이상 TIME 미수신) bit1 UNPROVISIONED bit2 LOW_BATT(<3.5 V)
HELLO       [mac 6B][fw u8][batt_mV u16 BE]   헤더 BLD=0x00 ROOM=0 UNIT=0 TXN=0
```

`type` 값(슬롯·예약 공통): 1=수업 2=시험 3=휴강 4=빈강의실 5=특강 6=**대여**. layout 매핑은 §6.3.

### 3.4 ACK status

| status | 의미 | 백엔드 처리 |
|---|---|---|
| 0x00 OK | 적용 완료 | acked |
| 0x01 BAD_CRC | 앱 CRC 불일치 | 재전송 |
| 0x02 BAD_PAYLOAD | 파싱 실패/길이 오류 | failed + 로그(코덱 버그 의심) |
| 0x03 STORE_FAIL | 파일시스템 기록 실패 | 재전송 1회 후 failed |
| 0x04 GAP | 적용은 했으나 `(NEW_VER - 이전 ver) mod 255 != 1` (중간 패치 유실). **FILE 세션에는 적용하지 않는다**(§3.3) | acked + **해당 kind FILE 재동기 큐잉** (pending 작업이 있어도 억제하지 않음) |
| 0x05 FILE_MISSING | detail = 첫 누락 seq | 해당 seq부터 FILE_DATA 재송 |
| 0x06 UNSUPPORTED | 모르는 TYPE/CMD | failed |
| 0x07 BUSY | 렌더 중 등으로 지금 처리 불가 | 5 s 후 재전송 |
| 0x08 DUP | 같은 TXN 재수신 — 재적용 없이 ACK만 | acked |

### 3.5 TXN·중복·순서

- 백엔드는 (room, unit)마다 TXN을 1~255 롤링. 단말은 마지막 TXN을 RTC/NVS에 보관, 같은 TXN 재수신 시 `DUP` ACK(멱등 보장).
- **TXN은 공중 프레임마다 하나씩 소비한다.** FILE 세션(BEGIN + DATA×n + END)은 n+2개의 TXN을 쓴다. 단말의 DUP 판정은 프레임 단위이므로 FILE_DATA 재송(FILE_MISSING 이후)은 **새 TXN**으로 보낸다. (2026-09-10 확정 — §8.4 의 "job 당 txn" 표현은 이 규칙으로 읽는다)
- 단말은 TYPE별 멱등 키: SLOT=(day,sH,sM), RESV=resvId, EXAM=examId.
- 프레임 순서는 백엔드 워커가 (room, unit) FIFO로 보장(§8.4).

---

## 4. 게이트웨이(모뎀) 펌웨어

### 4.1 역할
USB 시리얼(115200, JSON lines, UTF-8, `\n` 종단)로 호스트 명령을 받아 LoRa로 쏘고, 응답/업링크를 호스트로 올린다. **프레임 내용을 해석하지 않는다**(ACK 여부 판단만 헤더 플래그·TYPE으로).

### 4.2 호스트 → 모뎀

```json
{"op":"tx","id":17,"frame":"20 4B 05 45 03 25 01 07 1A …","wake":true,"ack_ms":3000}
{"op":"cfg","sf":9,"bw":125,"cr":5,"power":14,"freq":922.5,"wake_ms":3000}
{"op":"ping"}
{"op":"stats"}
{"op":"reset"}
```
- `frame`: 헤더~CRC8 전체 hex(공백 허용). 모뎀은 길이·CRC8만 검증(불일치 시 `error`).
- `wake`: true면 `RP_PREAMBLE_WAKE_MS` 프리앰블, false면 normal.
- `ack_ms`: 송신 완료 후 ACK 대기 시간. 0이면 대기 없음(TIME 등).
- `id`: 호스트 상관 ID. 응답에 그대로 에코.

### 4.3 모뎀 → 호스트

```json
{"op":"ready","fw":"gw-2.0.0","sf":9,"freq":922.5}                       // 부팅 시 1회
{"op":"tx_done","id":17,"status":"acked","rssi":-97,"snr":6.5,"ack":"20 4B 10 …","air_ms":4310}
{"op":"tx_done","id":17,"status":"no_ack"}
{"op":"tx_done","id":17,"status":"cad_busy","tries":5}
{"op":"tx_done","id":17,"status":"error","reason":"bad_crc8"}
{"op":"rx","rssi":-101,"snr":4.0,"frame":"20 4B 11 …"}                    // 비요청 업링크(STATUS/HELLO)
{"op":"pong","uptime_s":12345}
{"op":"stats","tx":120,"acked":117,"no_ack":3,"cad_busy":2,"rx":40}
{"op":"log","level":"warn","msg":"…"}
```

### 4.4 송신 절차 (한 `tx`당)

```
1. 프레임 검증(길이·CRC8)            실패 → tx_done error
2. CAD 루프: scanChannel()
     free   → 3으로
     busy   → 랜덤 백오프(50~200 ms) 후 재시도, RP_CAD_MAX_TRIES 초과 → tx_done cad_busy
3. setPreambleLength(wake? wake_syms : 8) → transmit(frame)
4. ack_ms == 0 → tx_done sent
   else startReceive(); ack_ms 동안 대기
     수신 프레임의 [NET_ID, TYPE==ACK, BLD/ROOM/UNIT/TXN == 송신 헤더] 일치 → tx_done acked (+rssi/snr/ack)
     불일치 프레임 → rx로 호스트에 전달하고 계속 대기
     타임아웃 → tx_done no_ack
5. startReceive() 로 복귀(업링크 상시 청취)
```
- 모뎀은 **한 번에 하나의 `tx`만** 처리한다. 진행 중 새 `tx`가 오면 `{"op":"tx_done","id":N,"status":"error","reason":"busy"}` 즉시 반환. 직렬화는 백엔드 책임.
- 재시도(재전송)는 하지 않는다. 백엔드가 정책을 가진다.

### 4.5 기타
- 워치독: 30 s 내 호스트 `ping` 없으면 라디오 재초기화(호스트 재기동 대비). 호스트는 10 s마다 `ping`.
- 부팅 시 Vext OFF(OLED 차단), Wi-Fi/BLE OFF.
- 시리얼 라인 최대 1,024 B. 파싱 실패 라인은 `log`로 알리고 무시.

---

## 5. 단말 펌웨어 — 저장·시각·상태 판단

### 5.1 파일시스템·영속 데이터

| 저장소 | 내용 | 비고 |
|---|---|---|
| NVS `cfg` | `bld`(u8) `room`(u16) `unit`(u8) `identVer` `provisioned`(bool) `statusHourUtc` `sessionWindowMs` | 정체성·파라미터 |
| NVS `ver` | `schedVer` `resvVer` `examVer` `lastTxn` | 버전·중복 방지 |
| LittleFS `/schedule.bin` `/resv.bin` `/exam.bin` | §3.3 FILE 본문과 동일한 레코드 스트림(바이너리) | JSON 폐지. 파싱 비용·메모리 절감 |
| RTC slow mem (`RTC_DATA_ATTR`) | 아래 구조체 | 딥슬립 간 캐시. 부팅 시 매직·CRC 검증 실패면 LittleFS/NVS에서 재구축 |

```c
typedef struct {
  uint32_t magic;            // 0xEPA2xxxx
  uint8_t  bld; uint16_t room; uint8_t unit; uint8_t provisioned;
  uint8_t  schedVer, resvVer, examVer, identVer, lastTxn;
  uint8_t  lastLayout; uint8_t lastDay; uint16_t lastSlotStartMin;   // 상태키
  uint32_t lastTimeSyncEpoch; uint32_t nextStatusEpoch;
  uint8_t  nSlots; Slot slots[48];        // 48 × 36 B ≈ 1.7 KB (subj 20B, prof 12B 고정 버퍼)
  uint8_t  nResv;  Resv  resv[24];        // 24 × 44 B ≈ 1.1 KB
  uint8_t  nExam;  Exam  exams[8];
  uint16_t crc;
} rtc_state_t;                           // 합계 < 4 KB (RTC slow 8 KB 내)
```
- 문자열은 고정 버퍼(UTF-8, 과목 20 B, 교수 12 B)로 잘라 저장. 화면 표시 한계와 일치.
- 용량 초과(슬롯 48개 초과 등) 시 `STORE_FAIL` ACK.

### 5.2 시계
- `settimeofday` + `TZ=KST-9`. 딥슬립 중에도 RTC 타이머가 계속 가므로 `time()`은 유지된다.
- `clockValid = (time() > 1_700_000_000)`. 유효하지 않으면 렌더 보류(e-Paper는 마지막 화면 유지).
- TIME 수신 시 `lastTimeSyncEpoch` 갱신. 25 h 초과 시 STATUS에 `CLOCK_STALE`. 렌더는 계속한다.
- 드리프트: 딥슬립 RC 클럭 기준 시간당 수 초 가능 → 매시 TIME으로 흡수. DS3231 도입은 실측 후 결정(비범위).

### 5.3 상태 판단 (`determineLayout`, v1 로직 유지)
우선순위 **예약 > 시험기간 > 기본 시간표**.
1. 예약: 오늘 날짜·현재 시각이 [start,end) 안이면 `typeToLayout(type)`.
2. 시험기간: 오늘이 기간 내이고 현재 시각이 어떤 슬롯 안이면 시험중(5).
3. 기본: 슬롯 안 & 분<50 → 수업중(1) / 슬롯 안 & 분≥50 → 쉬는시간(2) / 슬롯 밖 → 빈강의실(4).

| layout | 상태 | 색 | 비고 |
|---|---|---|---|
| 1 | 수업중 | RED | |
| 2 | 쉬는시간 | BLACK | |
| 3 | 휴강 | BLACK | |
| 4 | 빈강의실 | BLACK | |
| 5 | 시험중 | RED | |
| 6 | 특강 | RED | |
| **7** | **대여중** | RED | v2 신규. `StatusImages.h`에 "대여중" 이미지 추가(`generate_images.py` labels) |
| 8 | 설정 대기 | BLACK | 미설정 단말 화면: `NEW-xxxx`(MAC 하위 2 B) 표시 |

`typeToLayout`: 수업1→1, 시험2→5, 휴강3→3, 빈강의실4→4, 특강5→6, 대여6→7.

### 5.4 다음 변경 시각 (`nextChangeAt(now)`) — 신규
후보 중 최소값. 없으면 `now + 24 h`.
- 오늘·이후 7일 내 모든 슬롯의 start, end, 그리고 슬롯 안에 있을 때 다음 `:50:00`
- 모든 예약의 start, end (오늘 이후)
- 시험기간 시작일 00:00, 종료일 다음날 00:00
- 다음 자정(요일 전환)
- `nextStatusEpoch`
결과에 **+2 s 마진**을 더해 경계 직후에 깨도록 한다(드리프트로 경계 직전에 깨는 것 방지). 깨어난 뒤 상태키가 같으면 렌더 없이 재계산·재슬립.

---

## 6. 단말 펌웨어 — 상태머신·절전·통신

### 6.1 부팅 분기

```
setup():
  Vext OFF 유지, Wi-Fi/BLE OFF, Serial(디버그 빌드만)
  cause = esp_sleep_get_wakeup_cause()
  rtc 검증 실패 → NVS/LittleFS에서 rtc 재구축 (콜드 부팅 경로)
  라디오 init (begin → setParams → sync word → CRC on)
  switch(cause):
    TIMER  → handleTimer()
    EXT0(DIO1) → handleRadio()
    EXT1(GPIO0) → handleButton()
    UNDEFINED(콜드 부팅) → handleColdBoot()
  goToSleep()
```

### 6.2 handleColdBoot
1. 미설정(`provisioned==false`)이면 layout 8 렌더, `HELLO` 송신, `nextStatusEpoch = now + 10 min`.
2. 설정됨이면 `STATUS` 송신(부팅 보고) 후 `handleTimer()`와 동일 경로.

### 6.3 handleTimer
1. `clockValid` 아니면 goToSleep(다음 시도 10 min).
2. `now >= nextStatusEpoch` → STATUS 송신, `nextStatusEpoch = 다음날 statusHour + hash(mac)%1800 s`.
3. `layout = determineLayout(now)`; 상태키 `(layout, day, curSlotStart)` 비교. 다르면 `render(layout)`.
4. `sleepUntil = nextChangeAt(now)`.

### 6.4 handleRadio (DIO1 웨이크)
```
startReceive()                       // 프리앰블이 아직 공중에 있으므로 본문 수신 가능
loop (세션 창 sessionWindowMs, 기본 10 s, 프레임 수신 시마다 연장):
  frame = readData() if RX_DONE
  검증: NET_ID, CRC8, 대상(§6.6) — 불일치면 무시
  TXN == lastTxn → ACK(DUP) 후 continue
  dispatch(TYPE):
    TIME       → setClock, lastTimeSyncEpoch, flags.REQUEST_STATUS면 랜덤 지연 STATUS 예약
    SLOT_*/RESV_*/EXAM_* → apply(멱등) → 버전 검사(GAP?) → LittleFS 기록 → ACK(OK|GAP)
    FILE_BEGIN → 수신 버퍼 준비(kind,totalLen,nChunks) → ACK(OK)
    FILE_DATA  → seq 위치에 복사, 비트맵 갱신 → ACK(OK / FILE_MISSING)
    FILE_END   → crc16 검증 → kind 전체 교체 → LittleFS 기록 → 버전 갱신 → ACK(OK)
    CMD        → 실행 → ACK
    SET_ROOM   → MAC 일치 & 미설정 → 정체성 저장(NVS) → provisioned=true → ACK(OK) → 렌더 플래그
  ACK는 **렌더 전에** 송신 (렌더 7~20 s 동안 서버가 기다리지 않게)
  dirty 플래그 set
세션 창 종료 후: dirty면 handleTimer()의 3~4 수행(렌더는 최대 1회)
```
- 세션 창 안에서는 normal 프리앰블 프레임도 받는다(FILE_DATA/END는 normal로 온다).
- 렌더 중 수신은 하지 않는다(렌더 후 세션 창을 3 s 재개하여 밀린 프레임 1개 수용). 그 사이 온 프레임은 백엔드 재시도로 회복.

### 6.5 handleButton (GPIO0)
- 짧게(<1 s): `FORCE_RENDER` + STATUS 송신 (현장 확인용).
- 길게(≥5 s): `FACTORY_RESET` (정체성 삭제 → 미설정 상태). e-Paper에 카운트다운 표시.
- BLE 설정모드는 **v2에서 제거**. (필요 시 v2.1에서 옵션 빌드로 복원 가능하도록 `#ifdef FEATURE_BLE_SETUP` 자리만 남긴다.)

### 6.6 대상 필터
```
BROADCAST 플래그 → 수락
BLD==0x00 → 미설정 단말만: TYPE==SET_ROOM && payload.mac == myMac 이면 수락
그 외 → bld==myBld && room==myRoom && (unit==0 || unit==myUnit)
```
대상 불일치 프레임에는 **절대 응답하지 않는다**.

### 6.7 goToSleep(sleepUntil)
```
epd.hibernate(); Vext OFF
radio.startReceiveDutyCycleAuto(wakePreambleSymbols, RP_RX_DUTY_MIN_SYM)   // DIO1 = RX_DONE|PREAMBLE_DETECTED
rtc.crc 갱신
esp_sleep_enable_timer_wakeup((sleepUntil - now) µs)   // 최대 24 h
esp_sleep_enable_ext0_wakeup(GPIO14, HIGH)             // DIO1
esp_sleep_enable_ext1_wakeup(1ULL<<0, ESP_EXT1_WAKEUP_ANY_LOW)   // 버튼 (S3: ALL_LOW/ANY_HIGH 지원 여부 확인, 미지원 시 ext0를 버튼에, DIO1은 ext1 HIGH로)
esp_deep_sleep_start()
```
- **빌드 플래그 `SLEEP_MODE`**: `LIGHT`(1단계 검증용: `esp_light_sleep_start`, 리부팅 없음, 라디오 객체 유지) / `DEEP`(운영). 상태머신은 동일하고 진입·복귀 함수만 다르다.
- 딥슬립 웨이크 후 라디오는 `begin()`으로 재초기화한다(리셋 포함). 프리앰블 잔여 시간이 §2의 마진 안에 있으므로 본문 수신에 문제없음. 실측에서 미수신률이 5%를 넘으면 `RP_PREAMBLE_WAKE_MS`를 늘린다.

### 6.8 업링크 송신 규칙
- ACK/STATUS/HELLO는 normal 프리앰블, 송신 전 CAD 1회(busy면 30~120 ms 백오프 후 1회 더, 그래도 busy면 포기).
- 같은 호수 2유닛의 ACK 충돌은 백엔드가 유닛별로 따로 보내므로 발생하지 않는다. STATUS는 `hash(mac)` 랜덤 오프셋으로 분산.

### 6.9 렌더링
v1 자산 그대로 이식: `renderLayout`, `StatusImages.h`(+대여중, 설정 대기), `LabelImages.h`, `TimeGlyphs.h`, `NanumGothic20.h`, `KoreanFont.h`, GxEPD2 `GxEPD2_750c_Z08`(UC8179). 데이터 구조만 JSON → §5.1 바이너리 레코드로 바뀌므로 슬롯 탐색 함수(`findCurSlot` 등)를 구조체 배열 기준으로 재작성한다. 플래시 여유 확보를 위해 파티션은 `min_spiffs` 대신 **LittleFS 512 KB + 앱 3 MB**(S3 8 MB 플래시 기준 `custom.csv`).

---

## 7. 프로비저닝(초기설정) — LoRa 기반

```
[미설정 단말]                          [모뎀/백엔드]                         [관리자 웹]
 부팅 → layout 8 "NEW-3C7A" 표시
 HELLO(mac,fw,batt) ───────────────▶ rx → pending_devices upsert ──▶ "미등록 단말" 목록에 표시
 (10 min마다 HELLO, 그 사이 Rx duty)                                    관리자: 건물/호수/유닛 배정
                                    ◀── outbox SET_ROOM(mac, E,805,1)
 ◀──── SET_ROOM (wake) ────────────
 MAC 일치 → NVS 저장 → ACK(OK) ────▶ tx_done acked → devices 등록, pending 삭제
 layout 4/현재 상태 렌더                → FILE schedule/resv/exam 자동 큐잉(§8.5)
 ◀──── FILE_BEGIN/DATA/END … ──────
 STATUS ──────────────────────────▶ terminal_status 갱신
```
- HELLO 주기 10 min은 배터리 부담이 작다(패킷 1개). 설치 당일에만 발생.
- 같은 MAC에 두 번 SET_ROOM이 오면 마지막 것을 따른다(identVer 증가).
- 이미 설정된 단말을 다른 호수로 옮길 때: 관리자 웹에서 "재배정" → `CMD FACTORY_RESET` 후 위 절차, 또는 `SET_ROOM`을 BLD=0x00이 아닌 **현재 정체성 타겟**으로 보내는 변형을 허용한다(단말은 타겟 일치 시에도 SET_ROOM을 수락).

---

## 8. 백엔드 LoRa 서비스 (`server/lora_service/`)

### 8.1 모듈

| 파일 | 역할 |
|---|---|
| `codec.py` | 프레임 빌더/파서. `lora_proto`의 C 헤더와 상수 공유(§9). |
| `modem.py` | `pyserial` + asyncio. JSON lines 송수신, `tx()` 코루틴(응답 대기), `rx` 이벤트 스트림, 10 s `ping`, 재연결. |
| `models.py` | SQLAlchemy: `outbox`, `terminal_status`, `room_versions`, `pending_devices`, `lora_log`. |
| `worker.py` | outbox 소비 루프, 재시도, 버전 조정, TIME 스케줄러, 업링크 처리. |
| `api.py` | **웹 세션이 호출하는 유일한 진입점** (§8.6). |
| `config.py` | `LORA_PORT`, 무선 파라미터, 재시도 정책. |

### 8.2 테이블

```sql
CREATE TABLE outbox (
  id INTEGER PRIMARY KEY,
  bld TEXT NOT NULL, room INTEGER NOT NULL, unit INTEGER NOT NULL,   -- unit 0 = 호수의 모든 유닛으로 확장(삽입 시 유닛별 행으로 분해)
  type TEXT NOT NULL,                 -- 'SLOT_SET' … 'FILE' 'CMD' 'SET_ROOM' 'TIME'
  payload TEXT NOT NULL,              -- JSON (codec 입력)
  priority INTEGER NOT NULL DEFAULT 5,-- 0 TIME, 1 RESV, 3 SLOT/EXAM/CMD, 5 FILE
  state TEXT NOT NULL DEFAULT 'queued',   -- queued|sending|acked|failed|cancelled
  attempts INTEGER NOT NULL DEFAULT 0,
  next_try_at DATETIME, txn INTEGER, ack_status INTEGER, ack_detail INTEGER,
  rssi INTEGER, snr REAL, last_error TEXT,
  created_at DATETIME NOT NULL, sent_at DATETIME, acked_at DATETIME
);
CREATE INDEX ix_outbox_pick ON outbox(state, priority, next_try_at, id);

CREATE TABLE terminal_status (
  bld TEXT, room INTEGER, unit INTEGER,
  mac TEXT, fw INTEGER, batt_mv INTEGER, rssi INTEGER, snr REAL,
  sched_ver INTEGER, resv_ver INTEGER, exam_ver INTEGER, ident_ver INTEGER,
  layout INTEGER, clock_stale BOOLEAN, low_batt BOOLEAN, uptime_h INTEGER,
  last_seen_at DATETIME, last_ack_at DATETIME, last_status_at DATETIME,
  sync_state TEXT,                    -- 'synced' | 'pending' | 'resync' | 'unknown'
  PRIMARY KEY (bld, room, unit)
);

CREATE TABLE room_versions (
  bld TEXT, room INTEGER, kind TEXT,  -- 'schedule'|'resv'|'exam'
  ver INTEGER NOT NULL,               -- 1..255 롤링
  PRIMARY KEY (bld, room, kind)
);

CREATE TABLE pending_devices (
  mac TEXT PRIMARY KEY, fw INTEGER, batt_mv INTEGER, rssi INTEGER,
  first_seen_at DATETIME, last_seen_at DATETIME
);

CREATE TABLE lora_log (
  id INTEGER PRIMARY KEY, at DATETIME, dir TEXT, bld TEXT, room INTEGER, unit INTEGER,
  type TEXT, txn INTEGER, status TEXT, rssi INTEGER, snr REAL, air_ms INTEGER, frame_hex TEXT
);
```

### 8.3 버전 규칙
- 웹이 시간표/예약/시험기간을 바꾸면 `api.py`가 `room_versions[kind]`를 +1(255→1) 하고, 그 값을 `NEW_VER`로 outbox에 넣는다. 한 변경에 유닛이 2개면 두 행 모두 같은 `NEW_VER`.
- ACK/STATUS의 ver가 `room_versions`와 다르면 `sync_state='resync'`로 표시하고 해당 kind의 `FILE` 작업을 큐잉(이미 queued/sending 상태 FILE이 있으면 중복 금지).
- `GAP` ACK도 동일하게 FILE 큐잉.

### 8.4 워커 알고리즘

```
loop:
  job = SELECT … WHERE state='queued' AND (next_try_at IS NULL OR next_try_at<=now)
        ORDER BY priority, id LIMIT 1   -- 단, 같은 (bld,room,unit)에 'sending' 행이 있으면 건너뜀
  없으면 0.5 s 대기 후 반복
  state='sending'   # TXN 은 아래 각 tx() 호출마다 next_txn() 으로 새로 받는다 (§3.5)
  if type=='FILE':
      frames = codec.build_file(kind, records, new_ver)     # BEGIN + DATA×n + END
      순차 tx: BEGIN wake=True, DATA/END wake=False, 각 ack_ms=3000
      FILE_MISSING(seq) → 그 seq부터 재송(최대 2회)
      어느 단계든 no_ack 2회 연속 → 작업 실패 처리(아래 재시도)
  else:
      frame = codec.build(type, header, payload, txn)
      res = modem.tx(frame, wake=True, ack_ms=3000)   # TIME은 ack_ms=0
  결과:
    acked (OK|DUP)        → state='acked', terminal_status 갱신(ACK 필드), lora_log
    acked GAP             → 위 + FILE 큐잉
    acked BUSY            → next_try_at = now+5 s (attempts 증가 없음)
    no_ack / cad_busy     → attempts++ ; attempts<3 → next_try_at = now + [5, 20, 60][attempts-1] s, state='queued'
                             attempts>=3 → state='failed', sync_state='pending'
    error                 → state='failed', last_error
```
- **전역 단일 인플라이트**: 모뎀이 반이중이므로 워커는 한 번에 하나만 보낸다.
- TIME 스케줄러: 매시 `:00:05`에 `TIME` outbox 삽입(priority 0, bld=0xFF). 서버 부팅 직후 1회 추가. `REQUEST_STATUS` 플래그는 하루 1회(03:00)만 세운다.
- 실패 작업은 매일 04:00에 `queued`로 되돌려 1회 재시도. 그래도 실패면 그대로 두고 대시보드에 노출.

### 8.5 업링크 처리 (`rx` 이벤트)
- `STATUS` → `terminal_status` 갱신, ver 비교(§8.3), `clock_stale`이면 TIME 1회 타겟 재송(브로드캐스트 아님, wake).
- `HELLO` → `pending_devices` upsert.
- `ACK`인데 매칭되는 `sending` 작업이 없으면 로그만(늦게 온 ACK).

### 8.6 웹 세션이 쓰는 API (`lora_service/api.py`)

```python
# 모두 동기 함수. 내부에서 DB 트랜잭션 + 버전 증가 + outbox 삽입. 즉시 반환(전송은 워커).
def enqueue_slot_set(bld, room, day, start, end, type_, subject, professor, unit=0) -> list[int]  # outbox ids
def enqueue_slot_del(bld, room, day, start, unit=0)
def enqueue_day_clear(bld, room, day, unit=0)
def enqueue_resv_set(bld, room, resv_id, date, start, end, type_, subject, professor, unit=0)
def enqueue_resv_del(bld, room, resv_id, unit=0)
def enqueue_exam_set(bld, room, exam_id, date_start, date_end, unit=0)
def enqueue_exam_del(bld, room, exam_id, unit=0)
def enqueue_full_sync(bld, room, kinds=("schedule","resv","exam"), unit=0)   # 레코드는 웹의 DB에서 콜백으로 읽음(§8.7)
def enqueue_cmd(bld, room, cmd, args=b"", unit=0)
def provision(mac, bld, room, unit) -> int
def request_time_broadcast() -> int
def get_status(bld=None, room=None) -> list[TerminalStatus]
def get_pending_devices() -> list[PendingDevice]
def get_outbox(state=None, bld=None, room=None, limit=100) -> list[OutboxRow]
def cancel(outbox_id) -> bool
```

### 8.7 마스터 데이터 접근
LoRa 서비스는 시간표·예약·시험기간의 **원본을 갖지 않는다**(웹의 DB가 원본). `enqueue_full_sync`는 웹 세션이 등록한 콜백 `RecordProvider(bld, room, kind) -> list[Record]`를 호출해 레코드를 얻는다. 웹 세션은 서비스 시작 시 `lora_service.set_record_provider(fn)`을 한 번 호출한다. 이 한 줄이 두 세션의 유일한 결합점이다.

### 8.8 운영
- `systemd` 서비스 하나(FastAPI 프로세스 안에서 워커를 asyncio 태스크로 실행). 포트는 `LORA_PORT=/dev/ttyUSB0`(udev 규칙으로 `/dev/lora-modem` 심볼릭 링크 권장).
- 모뎀 끊김: 5 s 간격 재연결, 그동안 outbox는 쌓인다.

---

## 9. 코드 공유·레포 구조

```
epaper-v2/
├─ lora_proto/                 # 단일 진실원
│   ├─ radio_params.h          # §2 상수
│   ├─ proto.h                 # TYPE·status·레이아웃·오프셋 상수, 구조체
│   ├─ proto.py                # 같은 상수의 Python 미러 (CI에서 헤더 파싱해 diff 검사)
│   └─ test_vectors.json       # Python이 생성한 프레임 벡터 → C++ unity 테스트가 동일 결과 검증
├─ firmware/                   # PlatformIO, 두 env
│   ├─ platformio.ini          # [env:terminal] [env:modem] 공통 lib_deps: RadioLib, GxEPD2, ArduinoJson(모뎀만)
│   ├─ lib/lora_codec/         # 프레임 인코딩/디코딩 (양쪽 공용)
│   ├─ src/terminal/           # §5~7
│   ├─ src/modem/              # §4
│   ├─ src/fonts/              # v1에서 복사 + 대여중/설정대기 이미지 재생성
│   └─ test/                   # unity: codec, determineLayout, nextChangeAt
├─ server/
│   ├─ lora_service/           # §8
│   ├─ tools/generate_images.py, convert_font.py, NanumGothic.TTF   # v1 복사
│   └─ tests/                  # pytest: codec(벡터), worker(모뎀 fake), 버전 조정
└─ docs/
```

**v1에서 가져올 것**: `src/fonts/*`, `server/tools/*`, `determineLayout`·`renderLayout`·`drawTimeStr`·`ngPrintLine/Bold` 로직, `crc8`. **버리는 것**: `CMD_SCHED_BEGIN/DATA` 청크, `configureLoraHat`, `drainSerial2`, BLE 설정모드, `store.py` JSON 파일 저장, `SETUP_HTTPS.md`.

---

## 10. 검증 계획

### 10.1 단위
- `codec` 라운드트립: Python으로 각 TYPE 프레임을 만들고 `test_vectors.json`에 기록 → C++ unity가 파싱해 필드·CRC8 일치 확인, 역방향(C++ 빌드 → Python 파싱)도 동일.
- `determineLayout`·`nextChangeAt`: 경계값(정각, :50, 자정, 요일 전환, 예약과 시험기간 겹침, 대여 종료 직후).
- 워커: fake 모뎀으로 acked/no_ack/GAP/BUSY/FILE_MISSING 시나리오, 재시도 타이밍, 유닛 분해, 버전 조정.

### 10.2 벤치 (책상 위, 모뎀 + 단말 1대)
1. 깨어 있는 모드(`SLEEP_MODE=NONE`)로 전 TYPE 왕복.
2. `LIGHT` → `DEEP` 순으로 DIO1 웨이크 수신률 측정: wake 프레임 100회 송신, 미수신률 ≤ 5 % (초과 시 `RP_PREAMBLE_WAKE_MS` 상향).
3. 타겟 격리(다른 호수 프레임 무시), DUP(같은 TXN 3회), GAP(중간 패치 삭제 후 전송 → 자동 FILE 재동기), 재부팅 영속성.
4. 프로비저닝 전 과정.

### 10.3 필드 (P0, 부품 도착 직후)
- 게이트웨이 후보 위치에서 캠퍼스 끝 건물·지하·계단실까지 SF7/9/10 각 20패킷 RSSI/SNR/PER 측정. 결과로 `RP_SF`·안테나 위치 확정.

### 10.4 전력
- INA219/PPK2로 (a) 딥슬립 대기 전류 (b) 갱신 1회 전하량 (c) 24 h 실사용 소모. §1.4 목표 대비.

### 10.5 소크
- 강의실 3곳, 1주일. `terminal_status`의 `last_seen_at` 공백, `sync_state`, 배터리 기울기, 실패 outbox 수를 지표로.

---

## 11. 구현 단계

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| P0 | 부품 수령, RadioLib 원시 스케치로 SF 실측(§10.3) | `RP_SF` 확정 |
| P1 | `lora_proto` + codec(Python/C++) + 벡터 테스트 | CI 통과 |
| P2 | 모뎀 펌웨어(§4) + `modem.py` | `ping/tx/rx` 루프백 |
| P3 | 단말 펌웨어 **깨어 있는 모드**: 렌더 이식, 바이너리 저장, 전 TYPE 처리, ACK | 벤치 10.2-1,3 |
| P4 | 백엔드 `lora_service`(outbox, 워커, 버전, TIME, 업링크) | pytest + 실기 |
| P5 | `SLEEP_MODE=LIGHT` + DIO1 웨이크 + 세션 창 | 벤치 10.2-2(라이트) |
| P6 | `SLEEP_MODE=DEEP` + RTC 캐시 + Vext 게이팅 + 전력 실측 | §1.4 목표 |
| P7 | 프로비저닝(HELLO/SET_ROOM) + STATUS + 버튼 | 벤치 10.2-4 |
| P8 | 3실 소크 테스트, 배터리 케이스 조립 | §10.5 |

웹 세션은 P4의 `api.py` 시그니처(§8.6)와 테이블(§8.2)을 기준으로 병행 개발할 수 있다.

---

## 12. 에러·엣지 케이스

| 상황 | 처리 |
|---|---|
| 프리앰블 감지 후 본문 놓침 | 세션 창 10 s 동안 깨어 있음 → 백엔드 재시도(5 s 후)가 normal/wake 무관하게 수신됨 |
| 렌더 중 프레임 도착 | 미수신. 백엔드 재시도로 회복(BUSY ACK는 렌더 직전 도착 시에만) |
| 같은 호수 2유닛 | 백엔드가 유닛별 행으로 분해, 각자 TXN·ACK |
| 시계 미동기 콜드 부팅 | 렌더 보류, 10 min마다 타이머 웨이크로 재확인, 다음 정각 TIME으로 복구. STATUS에 CLOCK_STALE |
| 버전 롤오버(255→1) | 버전은 1~255 롤링(0=미정)이므로 단말은 `(new - old) mod 255 == 1`로 연속 판정 (mod 256이면 255→1이 GAP로 오판됨. 2026-09-10 정정) |
| 슬롯 48개/예약 24개 초과 | STORE_FAIL ACK → 백엔드 failed + 대시보드 경고. 예약은 서버가 **오늘~7일 이내만** 전송해 개수 억제 |
| 모뎀 USB 끊김 | outbox 적체, 재연결 후 순차 처리. TIME은 다음 정각에 |
| 다른 LoRa 실험 간섭 | NET_ID·동기워드로 필터, CAD 백오프 |
| 배터리 < 3.5 V | STATUS LOW_BATT → 대시보드. < 3.3 V면 렌더 중단하고 STATUS만(화면은 마지막 상태 유지) |
| 스푸핑 | v2 미대응(사설 동기워드·NET_ID만). v3: AES-128-CTR + CMAC 4 B 트레일러 검토 |

---

## 13. 가정·미결

- **가정 A**: 초기설정은 LoRa 프로비저닝으로 전환하고 BLE는 제거한다(§7). 거부 시 v1 BLE 코드를 `FEATURE_BLE_SETUP`로 복원.
- **가정 B**: STATUS는 일 1회(03:00 + 랜덤 ≤ 30 min) + 부팅·프로비저닝·버튼 시. 더 촘촘한 갱신은 `SET_PARAM statusHourUtc`로 조정 가능하지만 기본은 1회.
- **가정 C**: SF 실측(P0)을 프로토콜 구현 전에 수행하고, 그 전까지 SF9로 개발한다.
- **미결 1**: 917~923.5 MHz 대역의 허용 출력·LBT 세부 요건(전파법 고시) 확인 → `RP_TX_POWER_DBM` 상향 여부.
- **미결 2**: DTP105085 PCM 내장 여부(스펙시트) 및 Heltec V3 배터리 커넥터 극성.
- **미결 3**: ESP32-S3 `ext1` 웨이크 모드에서 ALL_LOW 지원 여부 → 미지원 시 DIO1/버튼의 ext0/ext1 배정을 교환(§6.7 주석).
- **미결 4**: 딥슬립 RTC 드리프트 실측값이 시간당 10 s를 넘으면 DS3231 추가 검토.
