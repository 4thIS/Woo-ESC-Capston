# S6 — 모뎀Pi LoRa 파이프라인 설계 (spec)

- 생성일시: 2026-09-10
- 수정일시: 2026-09-17 (r3 — cw-08 store 구현·리뷰 반영(로드맵 §4.3 "계약 ⑦ 구현"): 유닛 분해·`split` 삭제, 노드 안 FIFO는 store 의 `pick_next`가 보장, 비-FILE 재송은 `jobs.txn` 재사용, 기동 시 `recover()`, 쌓인 TIME 정리. r2 2026-09-16 — 계약 ⑦ 확정 반영: 동기 store, `split` 부모 `uploaded=1`, `set_meta/get_meta`로 `modem_fw` 전달, TXN 프레임 단위 확정. r1 2026-09-10)
- 상위 문서: `2026-09-09-roadmap-design.md` §3(책임 분할)·§4.3(계약 ⑦ JobStore)·§4.4(오프라인)·§4.5(v2 §8 개정). 워커 알고리즘 원본은 `2026-09-09-lora-v2-wor-design.md` §8.4 (이 문서로 이관), 모뎀 시리얼 프로토콜은 v2 §4.2·4.3, 프레임 규격은 v2 §3.
- 담당: cw @ssenu. 영역 `modempi/lora/`. 상대: `modempi/link/`(wj, S5)와는 `modempi/store.py`로만 만난다.

## 0. 배경 · 위치

모뎀Pi 안에서 "메인Pi가 준 작업(JSON)을 받아 → 전처리해서 → LoRa로 ESP노드에 쏘고 → 결과를 되돌려 놓는" 절반이다. 나머지 절반(WS로 받고 올리는 것)은 S5 링크. 둘은 SQLite 파일 하나(`JobStore`)를 사이에 두고 만나며 서로 import하지 않는다.

S1이 만드는 것에 의존한다: `lora_proto.codec`(프레임·페이로드·`build_file`), `modempi/lora/transport.py`(`LineTransport`), `modempi/lora/fake_modem.py`. 이 문서는 그 위에 얹는 것만 다룬다.

## 1. 목표 · 비목표

### 목표
- `JobStore`의 `received` 작업을 v2 §8.4 순서로 집어 `acked` 또는 `failed`로 끝낸다. 재시도·TXN·단일 인플라이트·FILE 청킹이 전부 여기 있다.
- 실물 모뎀(`modem.py`, pyserial)과 fake 모뎀을 **같은 `LineTransport`로** 다룬다. 워커 코드는 어느 쪽인지 모른다.
- 매시 TIME 브로드캐스트를 **자기 시계**로 낸다. 인터넷·메인Pi 없이도.
- 업링크(STATUS·HELLO)를 파싱해 `JobStore.put_uplink()`에 넣는다. 올리는 것은 링크.
- 4주차 Pi↔Pi 통합에서 fake 모뎀으로, 5~6주차에 실물 모뎀(S7)으로 같은 코드가 돈다.

### 비목표
- 시간표 원본·사본 보관. FILE 작업은 레코드를 **작업 안에** 들고 온다(로드맵 §1).
- 버전(NEW_VER) 부여, GAP 시 FILE 재동기 **생성** — 메인Pi. 여기는 GAP를 결과로 보고만 한다.
- WS·인증·재접속 — S5.
- 모뎀 펌웨어 자체 — S7.

## 2. 데이터 · 계약

- 계약 ⑦ `JobStore`(로드맵 §4.3) — **소비자**. 이 spec은 한 가지를 **additive로 추가**한다: 노드별 마지막 TXN을 재부팅 후에도 잃지 않기 위한 테이블. wj 리뷰 필요.
  ```sql
  CREATE TABLE IF NOT EXISTS node_txn (
    bld TEXT NOT NULL, room INTEGER NOT NULL, unit INTEGER NOT NULL,
    txn INTEGER NOT NULL,                 -- 마지막으로 쓴 TXN 1..255
    PRIMARY KEY (bld, room, unit)
  );
  ```
  인터페이스: `next_txn(bld, room, unit) -> int` (1..255 롤링, 0 건너뜀, 즉시 커밋). `store.py` 공용 파일이므로 PR에 양쪽 리뷰.
  추가(2026-09-16): `meta(key TEXT PRIMARY KEY, value TEXT)` 테이블 + `set_meta/get_meta`. 파이프라인이 모뎀 `ready.fw`를 `meta["modem_fw"]`에 쓰고, 링크가 `hello.modem_fw`로 올린다.
  **store는 동기(`sqlite3`)** — S5 spec §9 결정을 따른다. 파이프라인도 루프에서 직접 호출한다(ms 단위, 단일 연결). 링크 측 공식 시그니처는 `modempi/link/store_port.py`의 `JobStore` Protocol.
- 계약 ① 프레임 규격·② 모뎀 시리얼 — **소비자**. `lora_proto.codec`과 `LineTransport`만 쓴다.
- 계약 ⑥(WS)은 모른다.

## 3. 접근 제어 / 제약

- 모뎀은 반이중이고 §4.4대로 **한 번에 하나의 `tx`**만 받는다 → 워커도 **전역 단일 인플라이트**. 두 번째 `tx`를 보내면 모뎀이 `error busy`를 돌려주는데, 그건 워커 버그다(테스트로 잡는다).
- 에어타임: SF9 기준 wake 프레임 1개 ≈ 4.3 s. 같은 노드로의 연속 작업 사이에 추가 대기는 두지 않지만, ACK 대기(`ack_ms=3000`)가 끝나야 다음을 보낸다.
- `unit=0`(호수 전체)은 노드가 없다. 유닛 분해는 메인Pi `api._insert`가 하므로 여기 오지 않는다 — TIME이 아닌 `unit=0` 작업은 `failed(last_error="unit0")`로 닫는다(r3).
- 모뎀Pi RTC 없음 → NTP 동기 전엔 TIME을 내지 않는다(v2 §5.2 `clockValid`와 같은 기준: `time.time() > 1_700_000_000` 이고 최근 NTP 동기 성공).

## 4. 모듈

```
modempi/lora/
├── transport.py      # (S1) LineTransport
├── fake_modem.py     # (S1)
├── modem.py          # 실물: pyserial-asyncio 위 LineTransport. 포트 열기·ready 대기·cfg·10 s ping·재연결
├── modem_client.py   # LineTransport 위의 요청/응답 계층: tx(frame, wake, ack_ms) -> TxResult, rx 이벤트 큐, ping/stats
├── preprocess.py     # job(JSON) → 송신 단위 목록: FILE → [BEGIN, DATA…, END] 페이로드, 우선순위
├── worker.py         # JobStore 소비 루프: 픽업 → 프레임화(TXN) → 송신 → 결과 판정 → 재시도/완료
├── time_sched.py     # 매시 :00:05 TIME 행 생성, status_hour_utc 에 REQUEST_STATUS
├── uplink.py         # rx 프레임 파싱 → STATUS/HELLO → store.put_uplink(); 매칭 안 되는 ACK 는 로그
└── pipeline.py       # 위를 한 asyncio 태스크 묶음으로 기동/종료. main.py 가 이걸 부른다
```

### 4.1 `modem_client.py`

```python
@dataclass
class TxResult:
    status: Literal["acked", "no_ack", "cad_busy", "error", "sent"]
    ack: bytes | None = None       # acked 일 때 ACK 프레임 원본
    rssi: int | None = None
    snr: float | None = None
    air_ms: int | None = None
    tries: int | None = None       # cad_busy
    reason: str | None = None      # error

class ModemClient:
    def __init__(self, transport: LineTransport): ...
    async def start(self) -> None          # read_line 루프 시작, ready 수신까지 대기(최대 10 s)
    async def tx(self, frame: bytes, *, wake: bool, ack_ms: int) -> TxResult   # id 자동 증가, tx_done 매칭
    async def ping(self) -> int            # uptime_s
    async def cfg(self, **radio) -> None   # {"op":"cfg",...}
    rx: asyncio.Queue[RxEvent]             # RxEvent(frame: bytes, rssi: int, snr: float)
```
- `tx`는 **한 번에 하나만** 허용. 동시에 두 번 부르면 `RuntimeError` (설계 위반).
- `tx_done`의 `id`가 현재 요청과 다르면 로그만 남기고 무시(늦게 온 응답).
- `ready`가 다시 오면(모뎀 재부팅) `cfg`를 다시 보낸다.

### 4.2 `preprocess.py`

입력 `job` 행(계약 ⑦ 컬럼) → 출력 `list[Unit]`:
```python
@dataclass
class Unit:            # 송신 1회 단위
    store_id: str      # jobs.job_id
    bld: int; room: int; unit: int
    type: int          # P.Type
    payload_obj: object   # codec dataclass
    wake: bool
    ack_ms: int
    is_file_session: bool  # FILE 은 BEGIN/DATA/END 를 한 세션으로 묶어 처리
```
규칙:
- `unit == 0` 이고 TIME이 아님 → `failed(last_error="unit0")` (r3: 모뎀Pi 유닛 분해 삭제).
- `type == 'FILE'` → `payload.records`를 `codec` dataclass로 변환 → `build_file(kind, records, new_ver)` → `[FileBegin, FileData…, FileEnd]`. BEGIN만 `wake=True`, 나머지 `wake=False`(세션 창 안). `ack_ms=3000` 전부.
- `type == 'TIME'` → `wake=True, ack_ms=0`, 헤더 BROADCAST 플래그, `bld=0xFF room=0xFFFF unit=0 txn=0`.
- 그 외 변경 다운링크 → `wake=True, ack_ms=3000`, `ACK_REQ` 플래그.
- `payload` JSON 키는 `lora_proto.codec` dataclass 필드명과 같다(계약 ⑥ `job.payload` = codec 입력). 변환 실패 → `failed(last_error="bad_payload: …")`.

### 4.3 `worker.py` — v2 §8.4 그대로, 저장소만 JobStore

```
start: store.recover()        # sending→received, 재시도 대기 해제 (txn 유지)
loop:
  job = store.pick_next()     # 노드마다 머리 행만(메인 job_id 순 FIFO, 머리가 대기 중이면 노드 전체 대기),
                              # 노드끼리는 priority ASC, received_at ASC — store 가 보장 (로드맵 §4.3)
  없으면 0.5 s 대기
  if job.type == 'TIME': 더 오래된 TIME 행을 acked(last_error='superseded') 로 닫고, epoch 는 지금 시각으로
  units = preprocess(job)
  txn = job.txn or store.next_txn(...)   # 비-FILE: 첫 송신에서만 새 TXN. 재송(no_ack·BUSY·재기동)은 jobs.txn 재사용
  store.update(job.job_id, expect_state='received', state='sending', txn=txn)   # False 면 cancel 됨 → continue
  if FILE 세션:
      # TXN 은 프레임마다 (v2 §3.5 확정 2026-09-10): BEGIN/DATA/END 각각 next_txn(). FILE_MISSING 재송도 새 TXN
      for u in units: res = client.tx(frame(u, next_txn), wake=u.wake, ack_ms=3000)
          acked 이고 ACK.status==FILE_MISSING(seq) → 그 seq 부터 DATA 재송(최대 2회) 후 END 재송
          no_ack 2회 연속 → 세션 실패 → 아래 재시도 정책
          BUSY → 5 s 후 같은 프레임 재송(세션 유지)
      결과 = END 의 ACK
  else:
      res = client.tx(frame(u, txn), wake=True, ack_ms=3000 or 0)   # 같은 TXN 재송이어야 노드가 DUP 으로 받는다
  판정 (v2 §3.4·§8.4):
    sent                          → state='acked' (TIME)
    acked OK | DUP                → state='acked', ACK 필드 기록(ack_status, node_vers, batt, layout, fw, rssi, snr)
    acked GAP                     → state='acked', ack_status=GAP (메인이 FILE 큐잉)
    acked BUSY                    → next_try_at=now+5, state='received' (attempts 그대로)
    acked BAD_CRC                 → 재송 1회 → 그래도면 failed
    acked STORE_FAIL              → 재송 1회 → failed
    acked BAD_PAYLOAD|UNSUPPORTED → failed (codec 버그 의심, 로그 error)
    no_ack | cad_busy             → attempts+=1; <3 → next_try_at=now+[5,20,60][attempts-1], state='received'; ≥3 → failed, last_error
    error(reason)                 → failed, last_error=reason  (busy 는 워커 버그 → 예외로 올림)
  최종 update 는 expect_state='sending'. finished_at 은 store 가 채움. failed 로 닫을 땐 앞 시도의 ack_* 를 None 으로
```
- 실패 작업 매일 04:00 재시도(v2 §8.4)는 **메인Pi가 재큐잉**하는 것으로 옮긴다(모뎀Pi는 작업 원본이 없다). 여기서는 하지 않는다.
- `cancel_job()`으로 `cancelled`가 된 행은 pick하지 않는다.

### 4.4 `time_sched.py`
- 매시 `:00:05`에 `TIME` 행을 `put_job(job_id=f"time-{epoch}", type='TIME', priority=0, payload={"epoch": now, "flags": ...})`로 **스스로** 넣는다. `config.status_hour_utc`의 시각이면 `flags |= REQUEST_STATUS`.
- 시계가 유효하지 않으면(§3) 넣지 않고 경고 로그.
- 메인Pi의 `time_now` 메시지는 링크가 같은 `put_job`을 부르는 것으로 처리(S5).
- TIME 행은 `uploaded=1`로 만들어 링크가 메인에 보고하지 않게 한다(메인은 TIME 결과에 관심 없음).

### 4.5 `uplink.py`
- `client.rx` 큐를 소비. `decode_frame` 실패·NET_ID 불일치 → 로그.
- `STATUS` → `put_uplink({kind, bld, room, unit, mac:None, …ACK 필드, rssi, snr, flags, uptime_h})`.
- `HELLO` → `put_uplink({kind:'HELLO', bld:0, room:0, unit:0, mac, fw, batt_mv, rssi, snr})`.
- `ACK`가 `rx`로 오는 경우(늦은 ACK) → 로그만.
- `STATUS`의 `CLOCK_STALE` 플래그 → 그 노드에 **타겟 TIME 1회** 자체 큐잉(v2 §8.5). 헤더는 타겟 주소, `wake=True, ack_ms=0`.

### 4.6 `pipeline.py`
- `run(store_path, transport_factory, config_getter)`: `ModemClient.start()` → `cfg(config.radio)` → 태스크 3개(worker, time_sched, uplink) 기동. `on_config_changed`로 `cfg` 재전송 + 노드 목록 갱신.
- `transport_factory`가 fake면 `--fake` 모드. `main.py` CLI: `modempi --store /var/lib/modempi/jobs.db --port /dev/lora-modem` 또는 `--fake`.

## 5. 영역별 영향
- modempi/lora: 이 문서 전부. `store.py`(cw-08)에 `node_txn`·`meta`·`recover()`·`prune()` — 구현 완료, 로드맵 §4.3 "계약 ⑦ 구현".
- modempi/link (S5): `time_now` → `put_job(TIME)`. TIME 행은 `uploaded=1`. `job_result`는 메인 outbox 행(유닛별)마다 1건 — 모뎀Pi는 분해하지 않는다.
- server (S2): 04:00 실패 재큐잉을 메인Pi 쪽 규칙으로. `job.payload` 키 = codec 필드명 확인.
- firmware (S7): 모뎀 펌웨어는 이 spec의 `ModemClient`가 상대. 변경 없음.

## 6. 무회귀 · 롤아웃
- S1의 fake 모뎀 테스트가 이 워커의 회귀 테스트가 된다. 4주차 통합은 `--fake`로, S7 완료 후 `--port`로 바꾸는 것 외 코드 변경 없음.
- `store.py` 변경은 additive(테이블·컬럼 추가). 기존 컬럼 불변. `SCHEMA_VERSION` +1 + `_MIGRATIONS`.

## 7. 역할 분담
| 영역 | 담당 |
|---|---|
| `modempi/lora/*` | cw |
| `modempi/store.py` 추가분 리뷰 | wj |
| 계약 ⑥ 영향(§5) 반영 | wj (S2·S5 spec) |

## 8. 성공 기준
- fake 모뎀으로: acked/DUP/GAP/BUSY/BAD_CRC/STORE_FAIL/no_ack×3/cad_busy/FILE_MISSING 재송/ACK 유실 후 재송 = DUP(GAP 아님)/재기동 후 같은 TXN 재송/TIME 누적 → 1개만 송신/TXN 1→255→1/TIME 스케줄/CLOCK_STALE 타겟 TIME — 각 시나리오 pytest 1개 이상, 전부 녹색.
- `ModemClient.tx` 동시 호출이 `RuntimeError`.
- 4주차: 메인Pi 웹 저장 → 모뎀Pi(fake) `jobs.state='acked'` → `job_result` 업로드. 로컬 큐 100건을 연속 처리해도 `busy` 에러 0건.
- S7 이후: 실물 모뎀으로 같은 pytest 시나리오 중 하드웨어 무관 항목 통과, 벤치 v2 §10.2-1.

## 9. 열린 결정 (plan 단계)
- ~~FILE 세션 중 `BUSY`가 몇 번까지 허용되는지~~ → **확정(2026-09-23): 한 프레임당 5회**(`FILE_BUSY_MAX`). 초과하면 세션 실패로 보고 일반 재시도 정책(5·20·60 s, 3회)에 맡긴다 — 그냥 BUSY로 되돌리면 노드가 계속 바쁠 때 그 행이 노드 FIFO의 머리에 영원히 남아 같은 노드의 뒤 작업이 전부 막힌다.
- `next_txn` 롤링에서 0 건너뛰기 외에, 노드 `lastTxn`과 우연히 같아지는(255 주기) DUP 오판 — 프레임 간 최소 2개 이상 차이를 두는 규칙 필요 여부. 현재 v2 §3.5는 "같은 TXN 재수신 = DUP"만 정의.
- ~~`split` 대신 부모 행을 삭제할지~~ → r3에서 모뎀Pi 유닛 분해 자체를 삭제.
- ~~CLOCK_STALE 타겟 TIME이 노드 TXN을 소비하면 "재송은 같은 TXN" 가정이 깨진다~~ → **확정(2026-09-23): TIME은 브로드캐스트·타겟 모두 `txn=0`**, 노드는 TIME에 DUP 판정을 적용하지 않고 `lastTxn`도 갱신하지 않는다(v2 §3.5에 반영). 워커는 TIME이면 `next_txn()`을 부르지 않는다 — 모뎀Pi의 노드별 TXN 카운터도 소비되지 않는다. 노드 펌웨어(S8, cw)가 지켜야 할 규칙이다.
