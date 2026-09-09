# server — 영역 가이드

> 루트 `../CLAUDE.md`를 먼저 읽으십시오. 이 파일은 server 영역 특수 규칙만 다룹니다.
> 이 영역은 **메인Pi**에서 도는 서버입니다. 구현 근거는 로드맵 스펙 `../docs/specs/2026-09-09-roadmap-design.md` §3·§4.2·§4.5(v2 §8 개정)입니다. 워커·modem.py·codec은 여기 없고 `modempi/`에 있습니다.

## 스택

- 언어/런타임: Python 3.12 / FastAPI
- 패키지 매니저: **uv** (다른 매니저 사용 금지 — `uv add`로 추가하고 `uv.lock`을 커밋한다)
- 테스트: pytest
- 린트·포맷: ruff (`ruff check` + `ruff format`)

## 폴더 규칙

```
server/
├── lora_service/   # outbox·room_versions·api.py·RecordProvider·hub.py(WS 허브)·모뎀Pi 레지스트리 (보호 계층, PM 리뷰 필수)
├── api/            # FastAPI 라우터 — 학생/관리자 웹이 쓰는 HTTP 엔드포인트
├── tools/          # generate_images.py, convert_font.py (v1에서 이식)
└── tests/          # pytest: codec(벡터), 워커(모뎀 fake), 버전 조정
```

## 계층 책임

- `lora_service/`는 **무엇을 보낼지**(작업·NEW_VER)만 안다. 언제·어떻게 쏠지(TXN·재시도·프레임 바이트)는 모뎀Pi의 책임이므로 여기서 흉내내지 않는다. `outbox.state`는 `queued → dispatched → acked|failed|cancelled`이고 `dispatched`는 재전송하지 않는다(로드맵 §4.2).
- `lora_service/`가 외부에 노출하는 것은 **`api.py`와 `set_record_provider`뿐**이다. 웹 코드는 그 밖의 모듈(`worker`, `modem`, `codec`, `models`)을 import하지 않는다.
- 웹 라우터(`api/`)는 `lora_service/api.py`의 동기 함수만 호출한다. outbox 테이블을 직접 INSERT하지 않는다 — 버전 증가와 삽입이 한 트랜잭션이어야 하기 때문이다.
- 모든 상태 변경은 **멱등**이고 **버전이 붙는다**. 유실은 재전송이 아니라 재동기로 흡수한다(스펙 §8.3).
- 공통 인프라 계층은 도메인을 import하지 않는다(의존 방향 단방향 유지).

## 커밋 scope

- `feat(server):`, `fix(server):`

## 테스트

- 새 코드는 테스트 동반(TDD: 실패 → 구현 → 통과).
- WS 허브는 **fake 링크**(pytest 안의 WS 클라이언트)로 `hello/config/job/job_accepted/job_result` 왕복, `dispatched` 규칙, 24 h 오프라인 실패 처리를 덮는다. `server/tests/fake_hub.py`는 `modempi/` 링크 테스트가 재사용하므로 인터페이스를 함부로 바꾸지 않는다.
- 외부 의존(DB 등)은 mock보다 **테스트용 실물**(격리된 테스트 인스턴스)을 쓴다.
- codec 테스트(`lora_proto/test_vectors.json` 생성·검증)는 `modempi/`로 이동했다. 이 영역은 `lora_proto.proto`의 상수만 참조한다.

## 계약(Contract) 규칙

- 이 영역은 **모뎀Pi에 대한 계약 ⑥(WS 백홀)의 제공자**다. 메시지 형태의 소유자는 `hub.py`다. 모뎀Pi 쪽에서 변환하지 말고 여기를 고치고 로드맵 §4.2에 반영한다.
- 이 영역은 **웹에 대한 계약의 제공자**다. `lora_service/api.py` 시그니처와 HTTP 응답 스키마의 소유자는 여기다. 웹이 형태를 바꿔달라고 하면 웹에서 변환하지 말고 여기를 고친다.
- 이 영역은 `lora_proto/`의 **소비자**다. 프로토콜 상수를 재정의하지 않는다.
- 새 응답 필드는 **additive**로 추가한다(기존 필드 불변) — 그래야 웹 배포 시점을 분리할 수 있다.
- DB 마이그레이션은 그 컬럼을 쓰는 코드보다 **먼저** 머지한다(lockstep).
- `lora_service/` 아래 테이블(`outbox`·`terminal_status`·`room_versions`·`pending_devices`·`modems`·`lora_log`) 마이그레이션은 파일명 prefix `lora_`, 나머지는 `web_`. `lora_` 마이그레이션은 PM 리뷰 필수.

## 절대 하지 말 것

- 다른 영역 디렉토리(`firmware/`, `web/`) 수정 금지 — 필요 시 이슈로 요청.
- `lora_proto/` 직접 수정 금지 (PM 전담).
- `lora_service/` 수정 시 PM 리뷰 필수 — 여기가 모뎀Pi·웹 양쪽 계약의 접점이다.
- 무선 파라미터·NET_ID는 `modems` 테이블에서 `config` 메시지로 내려보내는 값이다. 코드에 하드코딩하지 않는다.
- 패키지 매니저·Python 버전 설정 임의 변경 금지.
- 응답 스키마 변경 시 웹 담당과 사전 협의 + PR에 BREAKING CHANGE 명시.
