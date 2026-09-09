# Woo-ESC-Capston — LoRa RoomSign

e-Paper와 LoRa 통신을 활용한 저전력 강의실 시간표·예약 게시 시스템 (캡스톤디자인).

- **메인Pi**: 웹서버 1대(FastAPI + Vue 3 관리자/학생 웹, DB 원본). 여러 학교의 모뎀Pi와 WebSocket으로 통신
- **모뎀Pi**: 학교 건물당 Raspberry Pi 1대 + Heltec V3 USB 모뎀. 메인Pi에서 받은 작업을 LoRa로 ESP노드에 송신
- **ESP노드**: 강의실 문마다 Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262) + 7.5" 3색 e-Paper, 딥슬립 + Rx Duty Cycle 웨이크

## 문서

- **[팀 구상도·실행 계획·체크리스트 (HTML)](docs/overview.html)** — 처음 합류하면 이것부터. 브라우저로 열면 체크리스트가 저장된다
- [v2 LoRa 송수신·절전 단말·게이트웨이 설계 스펙](docs/specs/2026-09-09-lora-v2-wor-design.md)
- [진행 로드맵 · 3계층 토폴로지 · 서브프로젝트 분해 · 영역 간 계약](docs/specs/2026-09-09-roadmap-design.md) — v2 스펙 §8을 대체

## 이전 프로토타입 (v1)

https://github.com/ssenu/esp32_e-paper_syllabus — 폰트·이미지 생성 도구와 렌더링 로직을 여기서 이식한다 (스펙 §9 참고).
