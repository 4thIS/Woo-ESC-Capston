"""worker · time_sched · uplink 를 한 묶음으로 기동/종료 (S6 spec §4.6).

- 메인Pi `config` 가 올 때까지 모뎀에 `cfg` 도, 프레임도 보내지 않는다. `config.radio`(계약 ⑥ 이름)는
  모뎀 시리얼 `cfg`(v2 §4.2 이름)로 옮겨 보낸다 — `radio_to_cfg`.
- NET_ID 는 프레임마다 `config["net_id"]` 에서 읽는다(로드맵 §3 — 메인Pi 가 학교마다 배정).
- 10 s 마다 `ping` (v2 §4.5 — 30 s 없으면 모뎀이 라디오를 재초기화한다).
- 자식 태스크의 `run(stop)` 은 sleep·큐 대기가 끝나야 `stop` 을 본다 — 그래서 멈출 땐 cancel 한다.
- 자식 하나가 예외로 죽으면 나머지를 멈추고 그 예외를 올린다(조용히 반쪽으로 돌지 않는다). 모뎀 읽기
  태스크(`ModemClient.wait_closed`)도 감시 대상이다(#37 리뷰 3).
- USB 순간 끊김은 죽을 일이 아니다 — 송신은 `modem_disconnected` 로 재시도, 핑·cfg 실패는 로그만.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine

from lora_proto import proto as P

from modempi.lora.clock import clock_trusted
from modempi.lora.modem_client import ModemClient
from modempi.lora.time_sched import TimeScheduler
from modempi.lora.transport import LineTransport
from modempi.lora.uplink import UplinkReader
from modempi.lora.worker import Worker
from modempi.store import SqliteStore

log = logging.getLogger("lora.pipeline")

PRUNE_EVERY_S = 86400.0
PRUNE_KEEP_S = 7 * 86400.0
PING_EVERY_S = 10.0  # v2 §4.5 — 모뎀 워치독은 30 s

# 계약 ⑥ `config.radio` 키 → v2 §4.2 모뎀 `cfg` 키. freq 는 config 에 없어 lora_proto 에서 온다.
_RADIO_TO_CFG = {"sf": "sf", "bw": "bw", "cr": "cr", "tx_dbm": "power"}


def radio_to_cfg(radio: dict) -> dict:
    """메인Pi `config.radio`(`sf, bw, cr, tx_dbm, preamble_wake_ms`)를 모뎀 `cfg` 인자
    (`sf, bw, cr, power, freq, wake_ms`)로. 키가 빠졌으면 `KeyError` — 반쪽 설정은 보내지 않는다."""
    cfg = {op_key: radio[key] for key, op_key in _RADIO_TO_CFG.items()}
    cfg["freq"] = P.RADIO["RP_FREQ_MHZ"]
    cfg["wake_ms"] = radio["preamble_wake_ms"]
    return cfg


class Pipeline:
    """모뎀 하나에 붙는 LoRa 파이프라인. `run(stop)` 이 끝나면 모뎀 전송도 닫혀 있다."""

    def __init__(
        self,
        store: SqliteStore,
        transport: LineTransport,
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable] = asyncio.sleep,
        clock_ok: Callable[[float], bool] = clock_trusted,
    ) -> None:
        self.store, self._transport = store, transport
        self._clock, self._sleep, self._clock_ok = clock, sleep, clock_ok
        self._config_changed = asyncio.Event()
        self._sent_cfg: dict | None = None
        # 콜백은 링크 수신 루프 안에서 불린다 — 신호만 세우고 await 하지 않는다(PR #29 리뷰).
        # run() 을 여러 번 불러도 콜백이 쌓이지 않게 생성 때 한 번만 건다.
        self.store.on_config_changed(lambda _cfg: self._config_changed.set())

    def net_id(self) -> int:
        """지금 config 의 NET_ID. config 에 없을 때만 lora_proto 기본값."""
        return (self.store.get_config() or {}).get("net_id", P.NET_ID)

    async def run(self, stop: asyncio.Event) -> None:
        client = ModemClient(self._transport)
        tasks: list[asyncio.Task] = []
        try:
            await client.start()
            if client.fw:
                self.store.set_meta("modem_fw", client.fw)  # 링크가 hello 에 실어 올린다(계약 ⑦)
            # 읽기 태스크가 죽으면 이후 요청이 전부 타임아웃이다 — 자식처럼 감시해 전체를 멈춘다.
            tasks.append(self._spawn(client.wait_closed(), "modem_reader"))
            tasks.append(self._spawn(self._ping_loop(client, stop), "ping"))  # config 대기 중에도
            if not await self._wait_config(stop, tasks):
                return
            await self._apply_config(client)
            worker = Worker(
                self.store,
                client,
                clock=self._clock,
                sleep=self._sleep,
                clock_ok=self._clock_ok,
                net_id=self.net_id,
            )
            sched = TimeScheduler(
                self.store, clock=self._clock, sleep=self._sleep, clock_ok=self._clock_ok
            )
            reader = UplinkReader(self.store, client, clock=self._clock, net_id=self.net_id)
            tasks += [
                self._spawn(worker.run(stop), "worker"),
                self._spawn(sched.run(stop), "time_sched"),
                self._spawn(reader.run(stop), "uplink"),
                self._spawn(self._config_loop(client, stop), "config"),
                self._spawn(self._prune_loop(stop), "prune"),
            ]
            await self._until_stop_or_crash(stop, tasks)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await client.stop()

    @staticmethod
    def _spawn(coro: Coroutine, name: str) -> asyncio.Task:
        return asyncio.create_task(coro, name=f"lora.{name}")

    @staticmethod
    async def _until_stop_or_crash(stop: asyncio.Event, tasks: list[asyncio.Task]) -> None:
        stopper = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait([stopper, *tasks], return_when=asyncio.FIRST_COMPLETED)
        finally:
            stopper.cancel()
        for t in done:
            if t is not stopper and not t.cancelled() and t.exception() is not None:
                log.error("파이프라인 태스크 %s 가 죽었다 — 전체를 멈춘다", t.get_name())
                raise t.exception()

    async def _wait_config(self, stop: asyncio.Event, tasks: list[asyncio.Task]) -> bool:
        """config 가 있으면 True. 오기 전에 `stop` 이면 False. 기다리는 동안 자식(읽기·핑)이 죽으면
        그 예외를 올린다 — config 가 영영 안 오는 동안 반쪽으로 돌지 않게."""
        while self.store.get_config() is None:
            log.info("메인Pi config 대기 중 — 받을 때까지 송신하지 않는다")
            changed = asyncio.create_task(self._config_changed.wait())
            try:
                await self._until_stop_or_crash(stop, [changed, *tasks])
            finally:
                changed.cancel()
            if stop.is_set():
                return False
        self._config_changed.clear()  # 지금 읽을 config 가 최신 — _config_loop 가 한 번 더 보내지 않게
        return True

    async def _apply_config(self, client: ModemClient) -> None:
        cfg = self.store.get_config() or {}
        radio = cfg.get("radio")
        if radio is None:
            log.warning("config 에 radio 가 없다 — 모뎀 기본 무선 설정 유지")
            return
        try:
            params = radio_to_cfg(radio)
        except (KeyError, TypeError):
            log.error("config.radio 가 계약 ⑥ 모양이 아니다: %r — cfg 생략", radio)
            return
        if params == self._sent_cfg:
            return  # 노드 목록 등만 바뀜 — 모뎀 라디오를 괜히 다시 잡지 않는다
        await client.cfg(**params)
        self._sent_cfg = params
        log.info("모뎀 cfg 전송: %s", params)

    async def _config_loop(self, client: ModemClient, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._config_changed.wait()
            self._config_changed.clear()
            await self._apply_config(client)

    async def _ping_loop(self, client: ModemClient, stop: asyncio.Event) -> None:
        # ping 은 송신 중이면 순번을 기다린다(ModemClient) — tx 와 겹쳐도 RuntimeError 가 나지 않는다.
        while not stop.is_set():
            await self._sleep(PING_EVERY_S)
            if stop.is_set():
                return
            try:
                await client.ping()
            except TimeoutError:
                # 모뎀이 재부팅하면 다음 ready 에 ModemClient 가 마지막 cfg 를 다시 보낸다.
                log.error("모뎀 핑 무응답 — 모뎀이 살아 있는지 확인 필요")
            except OSError as e:
                # USB 가 빠졌다 — SerialTransport 가 재연결을 시도 중이다. 서비스를 재기동할 일은 아니다.
                log.error("모뎀 시리얼 끊김(%s) — 재연결 대기", e)

    async def _prune_loop(self, stop: asyncio.Event) -> None:
        # 기동 때 한 번 — 하루를 못 넘기고 재기동되는 Pi 도 정리되게. 이후 하루마다.
        while not stop.is_set():
            n = self.store.prune(older_than=PRUNE_KEEP_S)
            if n:
                log.info("오래된 행 %d 개 정리", n)
            await self._sleep(PRUNE_EVERY_S)
