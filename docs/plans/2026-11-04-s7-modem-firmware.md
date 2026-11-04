# S7 모뎀 펌웨어 — 구현 계획 (plan)

- 생성일시: 2026-11-04
- 기준 spec: `docs/specs/2026-09-09-lora-v2-wor-design.md` §2·§4 (모뎀 시리얼 프로토콜·송신 절차·워치독), 로드맵 cw-13

**Goal:** 모뎀Pi 에 USB 로 붙는 Heltec V3 의 정식 펌웨어 `[env:modem]` — v2 §4.2·4.3 시리얼 JSON lines 전부와 §4.4 송신 절차(CAD → 송신 → ACK 대기), §4.5 워치독.

**범위 (2026-11-04 결정 — "시연에 문제없는 수준"):**
- 넣는다: `tx`(CAD·wake 프리앰블·ACK 매칭·짝 아닌 프레임은 `rx`)·`cfg`(범위 검사 후 적용)·`ping`·`stats`·`reset`·비요청 업링크 `rx`·30 s 무 `ping` 시 라디오 재초기화·Wi-Fi/BT 끔.
- 무선 파라미터는 `cfg` 로 바꾼다(메인Pi `config.radio` → 모뎀Pi 가 보냄). **SF 를 바꿔도 모뎀 펌웨어는 다시 굽지 않는다.** 원거리 대응(SF 상향·중계 노드)은 실측(cw-12) 뒤 별도 — 여기서는 설정을 받는 그릇만.
- 넣지 않는다: 메시·중계, 4 s 체류 제한 강제(경고 없이 `air_ms` 만 보고), OLED.

**Architecture:**
- `lib/modem_core/` — 하드웨어 없는 순수 로직. `Modem` 이 시리얼 한 줄을 받아 §4.4 절차를 돌리고 응답 JSON 을 쓴다. 라디오·시계·시리얼은 인터페이스(`RadioPort`, `Host`)로 받는다 → `native` env 에서 가짜 라디오로 전 시나리오를 테스트한다.
- `src/modem/` — 실물 어댑터만: RadioLib SX1262(DIO1 인터럽트 송수신 — 2026-10-21 시험 교훈: 블로킹 transmit/receive 를 섞으면 송신이 사라진다), `Serial` 줄 버퍼, `ESP.restart`.
- `lib/lora_codec` 의 `decodeFrame`(길이·CRC8 검증)·`matchesAck` 를 그대로 쓴다. 프레임 내용은 해석하지 않는다(§4.1).
- 상대는 `modempi/modempi/lora/modem_client.py`·`fake_modem.py` — 응답 키·`status`·`reason` 값을 fake 모뎀과 같게 맞춘다(`bad_crc8`·`cad_busy`·`sent`·`acked`·`no_ack`).
- 출발점은 10/28 실기 E2E 에 쓴 `firmware/bringup/e2e/src/modem/main.cpp`(미커밋). 그 동작을 `Modem` 으로 옮기고 CAD·검증·워치독·stats·reset 을 더한다.

**Tech Stack:** PlatformIO / C++17, Arduino-ESP32(espressif32@7.0.1), RadioLib 7.1.2, ArduinoJson 7, Unity(native)

---

### Task 1: `lib/modem_core` 순수 도우미 + 테스트

**Files:** Create `firmware/lib/modem_core/modem_core.h`·`modem_core.cpp`, Test `firmware/test/test_modem_core/test_main.cpp`

**Interfaces:**
- `mc::RadioCfg{freq,bw,sf,cr,power,wakeMs}` · `mc::defaultCfg()`(= `radio_params.h`)
- `const char* mc::validateCfg(const RadioCfg&)` — 문제 없으면 `nullptr`. 범위: freq 917.0~923.5, bw ∈ {62.5,125,250,500}, sf 7~12, cr 5~8, power −9~14(KR920 상한), wakeMs 0~10000
- `uint16_t mc::wakeSymbols(const RadioCfg&)` — `wakeMs / (2^sf / bw) + 1` (SF9/BW125/3000 ms → 733)
- `int mc::hexDecode(const char*, uint8_t*, size_t)`(공백 허용, 홀수·초과 → −1) · `mc::hexEncode`

- [ ] 실패 테스트(733, 범위 밖 값 거절, hex 라운드트립) → 구현 → `pio test -e native -f test_modem_core` PASS

### Task 2: `mc::Modem` — §4.2·4.3·4.4·4.5

**Interfaces:**
- `class RadioPort { begin(cfg) · apply(cfg) · scanChannel()→Cad · transmit(buf,n,preambleSym) · listen() · receive(RxPacket&, timeoutMs)→bool }`
- `class Host { millis() · delayMs() · randomRange(lo,hi) · writeLine(const char*) · restart() }`
- `class Modem { boot() · handleLine(const char*, size_t) · poll() · stats() · cfg() }`

시나리오 테스트(가짜 라디오·가짜 시계):
- 부팅 `ready{fw,sf,freq}` · `ping`→`pong{uptime_s}` · `stats` · `reset`→재시작 · 모르는 op·파싱 실패·1,024 B 초과 → `log warn`
- `tx`: CRC 불량 → `error bad_crc8` · `ack_ms=0` → `sent{air_ms}` · wake 면 프리앰블 733, 아니면 8 · 짝 ACK → `acked{rssi,snr,ack,air_ms}` · 짝 아닌 프레임 → `rx` 후 계속 대기 · 없음 → `no_ack`
- CAD: busy 5회 → `cad_busy{tries:5}`·송신 없음·백오프 50~200 ms · busy 2회 후 free → 송신
- `cfg`: 정상 → 적용·`wakeSymbols` 반영 · 범위 밖 → `log warn`·이전 값 유지
- 워치독: 30 s 동안 `ping` 없으면 `begin` 재호출 + `log warn`, 10 s 마다 `ping` 이면 없음
- `poll()`: 비요청 업링크 → `rx`

### Task 3: `[env:modem]` + `src/modem/` 실물 어댑터

**Files:** Modify `firmware/platformio.ini`, Create `firmware/src/modem/main.cpp`·`radio_sx1262.h`

- `[env:modem]`: espressif32@7.0.1 · heltec_wifi_lora_32_V3 · arduino · RadioLib 7.1.2 · `build_src_filter = +<modem/>` · 호스트 전용 lib 제외
- `pio run -e modem` 성공

### Task 4: 실기 확인 + PR

- 모뎀Pi 의 모뎀 보드에 굽고(`esptool merge_bin` → `scp` → `uvx esptool write_flash 0x0`), `modempi` 서비스로 웹 저장 → 노드 `acked` 왕복, `stats`·워치독(서비스 정지 30 s 뒤 `log`) 확인. 결과를 PR 에 첨부.
- 게이트: `pio test -e native` 전체, `pio run -e modem`, `pio check`(lib/·test/)
