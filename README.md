# Woo-ESC-Capston — LoRa RoomSign

e-Paper와 LoRa 통신을 활용한 저전력 강의실 시간표·예약 게시 시스템 (캡스톤디자인).

- 단말: Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262) + 7.5" 3색 e-Paper, 딥슬립 + Rx Duty Cycle 웨이크
- 게이트웨이: Heltec V3를 USB 시리얼 모뎀으로, 호스트는 Raspberry Pi
- 서버: FastAPI + Vue 3 (관리자/학생 웹), LoRa 서비스 계층은 `outbox` / `terminal_status` 계약으로 분리

## 문서

- [v2 LoRa 송수신·절전 단말·게이트웨이 설계 스펙](docs/specs/2026-09-09-lora-v2-wor-design.md)
- [진행 로드맵 · 서브프로젝트 분해 · 영역 간 계약](docs/specs/2026-09-09-roadmap-design.md)

## 이전 프로토타입 (v1)

https://github.com/ssenu/esp32_e-paper_syllabus — 폰트·이미지 생성 도구와 렌더링 로직을 여기서 이식한다 (스펙 §9 참고).
