# modempi — 영역 가이드

> 루트 `../CLAUDE.md`를 먼저 읽으십시오. 이 파일은 modempi 영역 특수 규칙만 다룹니다.
> 구현 근거는 `../docs/specs/2026-09-09-roadmap-design.md` §3·§4.2·§4.3·§4.4 (토폴로지·계약 ⑥·⑦·오프라인)와 v2 스펙 §8.4(워커 알고리즘, 이곳으로 이관)입니다.

## 이 영역이 무엇인가

**모뎀Pi**(학교 건물당 1대의 Raspberry Pi)에서 도는 Python 서비스. 메인Pi에서 WebSocket으로 작업을 받아 로컬에 보관하고, 전처리해서 USB로 붙은 Heltec 모뎀을 통해 ESP노드에 LoRa로 쏜다. 시간표 원본을 갖지 않는다 — 받은 작업만 안다.

## 스택

- 언어/런타임: Python 3.12 / asyncio
- 패키지 매니저: **uv** (다른 매니저 사용 금지 — `uv add`로 추가하고 `uv.lock`을 커밋한다)
- 테스트: pytest
- 린트·포맷: ruff
- 주요 의존: `websockets`(링크), `pyserial-asyncio`(모뎀), `sqlite3`(JobStore — 동기, S5 spec §9), `lora_proto`(codec 상수)

## 폴더 규칙 · 소유권 분할

```
modempi/
├── store.py         # 계약 ⑦ JobStore — SQLite jobs/uplinks/config 테이블 + 얇은 인터페이스 (공용, 변경은 양쪽 협의)
├── link/            # wj @leemonta9482 — WS 클라이언트·인증·재접속·job 수신→store·결과/업링크 업로드·config 수신
├── lora/            # cw @ssenu — store 소비·전처리(FILE 청킹)·워커(TXN·재시도·노드 FIFO)·modem.py·TIME 스케줄러·업링크 파싱·fake_modem.py
├── main.py          # 두 asyncio 태스크를 한 프로세스에서 기동. systemd 서비스 1개
└── tests/           # pytest: link는 fake 허브, lora는 fake 모뎀
```

| 경로 | 담당 |
|------|------|
| `link/` | wj |
| `lora/` | cw |
| `store.py`, `main.py` | 공용 — 바꾸려면 상대와 사전 협의, PR에 양쪽 리뷰 |

## 계층 책임

- **`link/`와 `lora/`는 서로 import하지 않는다.** 둘 사이의 유일한 통로는 `store.py`(SQLite 파일 하나)다. 링크는 `put_job/cancel_job/pending_results/mark_uploaded/set_config/pending_uplinks/mark_uplinks_uploaded/get_meta`, 파이프라인은 `recover/pick_next/get_job/update/next_txn/get_config/on_config_changed/put_uplink/set_meta/prune`만 쓴다. 구현은 `modempi/modempi/store.py`의 `SqliteStore`(로드맵 §4.3 "계약 ⑦ 구현").
- `link/`는 프레임·무선을 모른다. 받은 `job` JSON을 검증 없이 그대로 저장한다(검증은 파이프라인이 codec으로 한다). 메인Pi에 올릴 결과도 `store`에 있는 그대로 올린다.
- `lora/`는 인터넷·메인Pi·인증을 모른다. `store`에서 `received`를 집어 `acked`/`failed`로 끝내는 것이 전부다. TIME 행은 스스로 만든다(매시 `:00:05`, NTP 시계 기준).
- `lora/modem.py`는 실물 시리얼과 `fake_modem.py`를 같은 인터페이스(`tx()`, `rx` 스트림, `ping`)로 다룬다. 워커 코드는 어느 쪽인지 모른다.
- 상수(`NET_ID`, 무선 파라미터, 프레임 오프셋)는 `lora_proto`와 메인Pi의 `config` 메시지에서만 온다. 여기서 재정의하지 않는다.

## 커밋 scope

- `feat(modempi):`, `fix(modempi):`

## 테스트

- 새 코드는 테스트 동반(TDD: 실패 → 구현 → 통과).
- `link/`: fake 허브(`server/tests/fake_hub.py` 재사용)로 `hello → config → job → job_accepted → job_result` 왕복, 끊고 재접속 시 `pending_results` 몰아 보내기, 토큰 불일치 시 종료.
- `lora/`: fake 모뎀으로 acked / no_ack / GAP / BUSY / FILE_MISSING / DUP / cad_busy, ACK 유실 후 같은 TXN 재송 = DUP, FILE 청킹과 `FILE_MISSING(seq)` 재송, TXN 1~255 롤링, TIME 스케줄.
- 두 태스크의 통합(`job → store → fake 모뎀 → job_result`)은 4주차 Pi↔Pi 통합에서 실기로 확인하고 결과를 PR에 첨부한다.

## 계약(Contract) 규칙

- 이 영역은 계약 ⑥(메인Pi ↔ 모뎀Pi WS)의 **소비자**다. 메시지 형태를 바꿔야 하면 `server/lora_service/hub.py`(제공 측)를 바꾸고 로드맵 스펙 §4.2에 반영한다. 여기서 임의 변환하지 않는다.
- 이 영역은 계약 ①·②(`lora_proto`, 모뎀 시리얼)의 **소비자**다. 재정의 금지.
- 계약 ⑦(`store.py`)은 이 영역 **내부** 계약이다. 컬럼을 추가할 땐 additive로만(기존 컬럼 불변), 마이그레이션은 `store.py`의 `SCHEMA_VERSION`을 올린다.

## 절대 하지 말 것

- 다른 영역 디렉토리(`server/`, `firmware/`, `web/`) 수정 금지 — 필요 시 이슈로 요청.
- `lora_proto/` 직접 수정 금지 (PM 전담).
- `link/` ↔ `lora/` 상호 import 금지. `store.py` 우회해서 SQLite를 직접 열지 않는다.
- 시간표·예약 원본을 모뎀Pi에 저장하지 않는다(로드맵 §1 비목표). FILE 작업에 온 레코드는 그 작업이 끝나면 버린다.
- 무선 파라미터·NET_ID를 코드에 하드코딩하지 않는다 — `config`에서만.
