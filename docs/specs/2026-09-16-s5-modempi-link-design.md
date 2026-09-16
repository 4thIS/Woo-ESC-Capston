# S5 — 모뎀Pi 링크 (메인Pi ↔ 모뎀Pi WebSocket 클라이언트) — 설계 (spec)

- 생성일시: 2026-09-16
- 수정일시: 2026-09-16
- 상위 문서: `2026-09-09-roadmap-design.md` §3(책임 분할)·§4.2(계약 ⑥ + 메시지 인코딩 규칙)·§4.3(계약 ⑦ JobStore)·§4.4(오프라인)·§4.5(프로세스 1개). 제공 측은 `2026-09-14-s2-server-design.md` §2.4(허브 동작 규칙). 파이프라인 쪽 상대는 `2026-09-10-s6-modempi-lora-pipeline-design.md`(§4.4 TIME 행 `uploaded=1`, §5 링크 영향).
- 담당: wj @leemonta9482. 영역 `modempi/link/`. `modempi/store.py`(공용)는 cw-08 — 이 spec은 그 인터페이스의 **소비자**다.

## 0. 배경 · 위치

모뎀Pi 안에서 "메인Pi에서 WS로 작업을 받아 로컬에 보관하고, 파이프라인이 끝낸 결과·업링크를 메인Pi에 올리는" 절반이다. 나머지 절반(LoRa 송신)은 S6. 둘은 `store.py`(SQLite 파일 하나) 사이에 두고 만나며 서로 import하지 않는다.

메인Pi 허브(S2, PR #5 머지)는 이미 있다. 이 spec은 그 허브의 **거울**이다: 허브가 보내는 것을 받아 store에 넣고, store에 쌓인 것을 허브가 기대하는 형태로 올린다. 인코딩 규칙(로드맵 §4.2 표)은 여기서 재정의하지 않는다.

`store.py`(cw-08)가 아직 없으므로 링크가 요구하는 인터페이스를 `store_port.py`에 Protocol로 선언하고, 테스트는 메모리 fake로 한다. cw-08 실물이 이 Protocol을 만족하는지 리뷰로 확인한다.

## 1. 목표 · 비목표

### 목표
- 계약 ⑥ 메시지 10종을 소비 측에서 그대로 구현: `hello` → `config` → `job`/`cancel`/`time_now`/`ping` 수신, `job_accepted`/`job_result`/`uplink`/`pong` 송신.
- 끊기면 백오프로 재접속하고, 끊긴 동안의 결과는 쌓였다가 재접속 직후 몰아서 올라간다(로드맵 §4.2·§4.4). 중복 보고는 서버가 멱등 처리하므로 "최소 1회 전달"만 보장한다.
- 파이프라인과는 `store.py`로만 만난다. 프레임·codec·무선을 모른다.
- `server/tests/fake_hub.py`를 상대로 하드웨어·서버 없이 pytest로 검증한다. 4주차 Pi↔Pi 통합에서 실제 허브에 붙는다.

### 비목표 (이번엔 안 함 / 후속)
- 프레임 검증·TXN·재시도·TIME 매시 스케줄 — 파이프라인(S6). 링크는 `job.payload`를 검증 없이 저장한다(modempi/CLAUDE.md).
- 시간표 사본 보관(로드맵 §1). 받은 작업만.
- 자체서명 TLS·인증서 옵션 — S11 배포 시. 지금은 URL이 `ws://`든 `wss://`든 라이브러리 기본.
- 메트릭·대시보드 — 로그로 충분.
- `store.py` 자체 — cw-08.

## 2. 데이터 · 계약

- `lora_proto/` 프로토콜 정의 변경: **아니오**. 상수도 쓰지 않는다(파이프라인 몫). `TimeFlag.REQUEST_STATUS`만 `time_now` 처리에 참조.
- DB 스키마·마이그레이션 변경: **아니오**. 계약 ⑦ 테이블은 cw-08.
- 서버 응답 스키마 변경: **아니오**.
- 계약 ⑥ 변경: **아니오**. 로드맵 §4.2 표 + 인코딩 규칙 표를 그대로 소비한다.
- 계약 ⑦: **소비**. 링크가 쓰는 함수 7개를 §4.1 Protocol로 고정. 동기/비동기 여부는 §9 열린 결정.

### 2.1 계약 ⑥ 소비 규칙

| `t` (메인 → 모뎀Pi) | 처리 | store |
|---|---|---|
| `config` | 그대로 저장. 파이프라인은 `on_config_changed`로 읽는다 | `set_config(dict)` |
| `job` | 검증 없이 저장. `job_id`는 정수로 오므로 `str(int(job_id))`로 TEXT 저장. **같은 `job_id` 재수신은 무시**(서버 5 s 안전망·재접속 재송 대비, 멱등) — 무시했어도 `job_accepted`는 회신 | `put_job(...) -> bool` |
| `cancel` | `received`면 cancelled. 아니면 무시 — 파이프라인이 이미 잡았으면 그 결과가 올라간다 | `cancel_job(job_id) -> bool` |
| `time_now` | TIME 행을 링크가 직접 넣는다(S6 §4.4). `request_status`면 `flags |= TimeFlag.REQUEST_STATUS`. `uploaded=1`로 넣어 결과를 보고하지 않는다 | `put_job(job_id=f"time-{epoch}", type="TIME", priority=0, payload={"epoch","flags"}, uploaded=1)` |
| `ping` | `pong` 즉시 회신 | — |
| 그 외 / JSON 아님 | 로그, 무시, 연결 유지 | — |

| `t` (모뎀Pi → 메인) | 언제 | 내용 |
|---|---|---|
| `hello` | 접속 직후 1회 | `modem_id`, `token`, `agent_ver`(패키지 버전), `modem_fw`(`store.get_meta("modem_fw")` — 파이프라인이 모뎀 `ready.fw`를 기록, 없으면 `"unknown"`), `pending_results` = `len(store.pending_results())` |
| `job_accepted` | `job` 수신 직후 (저장 성공·중복 무관) | `job_id: int` |
| `job_result` | 업로더가 `pending_results()`에서 집어서 | `job_id:int, state, ack_status, ack_detail, attempts, txn, rssi, snr, sched_ver, resv_ver, exam_ver, ident_ver, batt_mv, layout, fw, last_error, finished_at(epoch int)`. `node_vers` JSON을 풀어 4개 `*_ver`로. `cancelled` 행은 `state="failed", last_error="cancelled"` |
| `uplink` | 업로더가 `pending_uplinks()`에서 집어서 | 파이프라인이 넣은 dict 그대로(`kind, bld, room, unit, mac, ACK 필드 평탄화, rssi, snr, flags, uptime_h`) |
| `pong` | `ping` 받으면 | — |

### 2.2 연결 규칙

- 백오프: 1 → 2 → 4 → 8 → 16 → 30 s 상한, ±20 % 지터. 접속 성공(=`config` 수신) 시 리셋.
- 인증 실패(close 4001): 재시도해도 같으므로 **즉시 상한(30 s)** + 경고 로그 1회/시도. 토큰을 고치기 전까지 30 s마다 1회.
- hello 후 10 s 안에 `config`가 안 오면 실패로 보고 재접속(서버의 10 s hello 타임아웃의 거울).
- 서버가 30 s마다 `ping`을 보낸다. 링크는 스스로 ping을 보내지 않는다. **60 s 이상 서버 메시지가 없으면** 죽은 연결로 보고 닫고 재접속.
- SIGTERM/SIGINT → 소켓 정상 close → 태스크 종료. 업로드 중이던 배치는 `mark_uploaded` 안 됐으면 재접속 후 재송.

### 2.3 업로드 규칙 (`uploader.py`)

- **1 s 주기**로 `pending_results(limit=100)`·`pending_uplinks(limit=100)` 폴링. 연결이 없으면 폴링만 하고 송신하지 않는다.
- 송신 순서: `job_result` 먼저, 그다음 `uplink`. 한 행 = 메시지 1개.
- 서버가 수신 확인 메시지를 주지 않으므로(계약에 없음) **소켓 write 완료 즉시** `mark_uploaded([ids])` / `mark_uplinks_uploaded([ids])`. write 중 예외면 mark 안 함 → 재접속 후 재송. 서버는 끝난 행을 무시하므로(S2 §2.4) 중복 안전.
- 재접속 직후: hello의 `pending_results`가 개수를 알리고, 다음 폴링 tick부터 100건씩 올라간다.

## 3. 접근 제어 / 제약

- 토큰은 env(`MODEMPI_TOKEN`)로만. 로그에는 hello를 `token: "***"`로 마스킹. 저장하지 않는다.
- `link/`는 `lora/`를 import하지 않는다. `store.py`를 우회해 SQLite를 직접 열지 않는다(modempi/CLAUDE.md).
- `job.payload`는 문자열(JSON)로 저장한다 — 파싱·검증하지 않는다. 계약 ⑦ `payload TEXT`.
- `job_id` 왕복: 수신 `int` → 저장 `str` → 보고 `int(job_id)`. TIME 행의 `time-<epoch>`는 `uploaded=1`이라 보고 대상이 아니므로 `int()`에 걸리지 않는다. 만약 `int()` 실패 행이 `pending_results`에 오면 로그 + `mark_uploaded`로 치워 무한 재시도를 막는다.
- 메모리: 폴링 배치 ≤ 100건. 스토어 행 수는 파이프라인/메인 규칙이 제한.
- 시계: 링크는 `time_now`의 epoch를 자기 시계(`time.time()`)로 채운다. NTP 미동기 판단은 파이프라인(S6 §3)이 TIME 송출 시점에 한다.

## 4. 인터페이스 계약

### 4.1 모듈 (`modempi/modempi/link/`)

```
modempi/modempi/link/
├── __init__.py
├── store_port.py   # JobStore Protocol + JobRow/UplinkRow (계약 ⑦ 링크 측 7함수 + get_meta)
├── client.py       # LinkClient — 상태머신·hello·수신 루프·재접속·watchdog
├── uploader.py     # Uploader — 1 s 폴링 → job_result / uplink 송신 → mark_*
└── run.py          # env 읽어 LinkClient.run() 기동. main.py(공용)가 이걸 태스크로 띄운다 (cw-08 뒤 연결)
modempi/tests/
├── fake_store.py   # 메모리 JobStore
└── test_link_*.py  # 상대 = server/tests/fake_hub.py (sys.path 에 server/ 추가해 tests.fake_hub import)
```

### 4.2 `store_port.py` — 링크가 요구하는 계약 ⑦ 인터페이스

```python
@dataclass
class JobRow:      # 계약 ⑦ jobs 컬럼 중 보고에 쓰는 것
    job_id: str; state: str; attempts: int
    txn: int | None; ack_status: int | None; ack_detail: int | None
    rssi: int | None; snr: float | None
    node_vers: str | None        # JSON {"sched","resv","exam","ident"}
    batt_mv: int | None; layout: int | None; fw: int | None
    last_error: str | None; finished_at: float | None

@dataclass
class UplinkRow:
    id: int; body: dict          # 파이프라인이 put_uplink 한 dict 그대로

class JobStore(Protocol):
    def put_job(self, *, job_id: str, bld: str, room: int, unit: int, type: str,
                payload: str, priority: int, new_ver: int | None, uploaded: int = 0) -> bool: ...
    def cancel_job(self, job_id: str) -> bool: ...
    def pending_results(self, limit: int = 100) -> list[JobRow]: ...
    def mark_uploaded(self, job_ids: list[str]) -> None: ...
    def set_config(self, config: dict) -> None: ...
    def pending_uplinks(self, limit: int = 100) -> list[UplinkRow]: ...
    def mark_uplinks_uploaded(self, ids: list[int]) -> None: ...
```

- 이 시그니처는 로드맵 §4.3 링크 행의 함수명을 그대로 쓴다. 인자 순서·타입은 이 spec이 처음 고정하는 것이라 **cw-08과 맞춘다**(§9).
- `put_job`이 `False`(이미 있음)를 돌려주는 것이 멱등의 근거. 계약 ⑦ `jobs.job_id PRIMARY KEY`.

### 4.3 `client.py`

```python
class LinkClient:
    def __init__(self, store: JobStore, *, url: str, modem_id: str, token: str,
                 agent_ver: str, clock=time.time, sleep=asyncio.sleep): ...
    async def run(self) -> None      # 종료 신호까지 재접속 루프. 내부에서 recv_loop / uploader / watchdog TaskGroup
    async def stop(self) -> None
    state: Literal["DISCONNECTED", "CONNECTING", "CONNECTED"]
```
`clock`·`sleep` 주입은 테스트에서 백오프·60 s 무응답을 실제로 기다리지 않기 위함.

### 4.4 `run.py` / env

| env | 뜻 |
|---|---|
| `MODEMPI_MAIN_URL` | `wss://<메인Pi>/ws/modem` |
| `MODEMPI_ID` | `modem_id` (예 `mjc-eng`) |
| `MODEMPI_TOKEN` | 메인Pi `POST /api/lora/modems` 응답의 평문 토큰 |
| `MODEMPI_STORE` | SQLite 경로 (cw-08의 `store.py`가 연다) |

누락 시 기동 실패 + 어떤 변수가 없는지 메시지. systemd: `EnvironmentFile=/etc/modempi.env` (600).

## 5. 영역별 영향

- modempi/link: 이 문서 전부.
- modempi/store.py (cw-08): §4.2 Protocol을 만족해야 한다. `uploaded` 인자를 `put_job`이 받는 것(TIME 행용, S6 §4.4)과 `pending_results`가 `cancelled` 행도 돌려주는 것(finished_at 세팅 필요) — cw-08 리뷰 시 확인.
- modempi/lora (S6): 영향 없음. `time_now`→TIME 행은 S6 §5가 이미 링크 몫으로 적어 둔 것.
- server: 영향 없음. `server/tests/fake_hub.py`를 상대로 쓴다(인터페이스 additive 유지 약속, S2 §4.5).
- lora_proto: 없음 (`TimeFlag` 참조만).
- main.py (공용): cw-08 뒤 `link.run.main()`을 태스크로 추가 — 양쪽 리뷰.

## 6. 무회귀 · 롤아웃

- 기존 코드 없음. `server/tests/fake_hub.py`와 실제 허브(`hub.py`)가 같은 메시지를 말하므로, fake_hub로 통과하면 4주차 실기에서도 같은 코드가 돈다.
- 순서: ① spec ② `store_port.py` + fake_store + client/uploader + 테스트 ③ cw-08 머지 후 `run.py`·`main.py` 연결 + Protocol 일치 확인.

## 7. 역할 분담

| 영역 | 담당 |
|------|------|
| `modempi/link/*`, `tests/fake_store.py`, `tests/test_link_*` | wj @leemonta9482 |
| `modempi/store.py`가 §4.2를 만족하는지 | cw @ssenu (cw-08) + wj 리뷰 |
| `main.py` 태스크 연결 | wj, cw 리뷰 |

## 8. 성공 기준

- `uv run pytest` 녹색(modempi), ruff 통과. fake_hub 상대 테스트:
  - hello → config → `set_config` 호출
  - `job` 2건 → `put_job` 2회 + `job_accepted` 2회; 같은 `job_id` 재수신 → `put_job` False, `job_accepted`는 회신
  - `time_now` → TIME 행 `uploaded=1`, `request_status` → flags
  - `cancel` → `cancel_job` 호출, 연결 유지
  - finished 행 2 + uplink 1 → 1 s 내 `job_result` 2·`uplink` 1, `mark_*` 호출. `cancelled` 행 → `failed/cancelled`
  - fake_hub 종료 → 백오프 후 재접속 → hello `pending_results` = 미보고 수 → 곧 몰아서 올라감
  - 4001 → 재시도 간격 30 s로 점프 (clock/sleep 주입)
  - 60 s 무응답 → 재접속 (clock/sleep 주입)
  - env 누락 → 명확한 실패
- 4주차: 메인Pi 실기 허브에 붙어 `job → store → (fake 모뎀) → job_result → 대시보드 acked`, "끊고 붙이기" 통과.

## 9. 열린 결정 (plan 단계에서 확정)

- **store 동기/비동기 — 결정(2026-09-16): 동기.** 링크는 store 함수를 이벤트 루프에서 직접 부른다(서버 `hub.py`와 같은 전례, 연결 1개 공유, ms 단위 SQLite). `aiosqlite` 안 씀. cw-08이 다르게 가려면 이 spec §4.2와 링크 호출부(`_hello`, `_on_message`, `Uploader.flush_once`)를 함께 바꾼다.
- `put_job`의 `uploaded` 인자 vs `put_job` 뒤 `mark_uploaded` 호출 — 전자가 원자적이라 제안. cw-08과 협의.
- `pending_results`가 `cancelled` 행을 포함하려면 `cancel_job`이 `finished_at`을 세워야 한다 — cw-08 확인.
- 재접속 직후 몰아 보내기 상한(100건/1 s)이 충분한지 — 4주차 "끊고 붙이기"에서 확인.
