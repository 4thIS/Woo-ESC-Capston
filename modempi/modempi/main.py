"""모뎀Pi 서비스 진입점 — 링크(wj)와 파이프라인(cw)을 한 프로세스에서, `SqliteStore` 하나를 나눠 쓴다.

공용 파일(modempi/CLAUDE.md) — 바꿀 땐 양쪽 리뷰. 링크 설정은 env(S5 spec §4.4), store 경로는 `--store`
(기본 env `MODEMPI_STORE`)이고 main 이 연다(S5 spec §6 ③).

    modempi --store /var/lib/modempi/jobs.db --port /dev/lora-modem
    modempi --fake                      # 하드웨어 없이 — 가상 노드 = 메인Pi config 의 nodes

종료·오류 흐름 (systemd `Restart=always` 전제):
- 링크나 파이프라인 한쪽이 예외로 죽으면 다른 쪽을 멈추고 store 를 닫은 뒤 exit 1 → systemd 재기동.
- SIGTERM/SIGINT → 둘 다 정상 종료, exit 0. (링크가 `link.run.main` 안에서 같은 신호에 자기 핸들러를
  덮어 건다 — 그 경우 링크가 먼저 멈추고, `serve` 가 그걸 정상 종료 요청으로 보고 파이프라인도 멈춘다.)
- USB 순간 끊김은 여기까지 오지 않는다 — SerialTransport 가 재연결, 파이프라인은 재시도·로그만.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Callable

from modempi.link import run as link_run
from modempi.lora.fake_modem import FakeModem
from modempi.lora.modem import SerialTransport
from modempi.lora.pipeline import Pipeline
from modempi.lora.transport import LineTransport
from modempi.store import SqliteStore

log = logging.getLogger("modempi")

SHUTDOWN_TIMEOUT_S = 5.0  # 파이프라인이 stop 을 보고 모뎀을 닫기까지 기다리는 최대 시간


async def serve(
    store: SqliteStore,
    transport: LineTransport,
    *,
    stop: asyncio.Event | None = None,
    link: Callable[[SqliteStore], Awaitable[None]] | None = None,
) -> None:
    """링크(`link.run.main(store)`)와 파이프라인을 함께 돌린다.

    - `stop` 이 서거나 링크가 스스로 정상 종료하면(신호) 둘 다 멈추고 정상 반환.
    - 어느 한쪽이 예외로 끝나면 다른 쪽을 멈추고 그 예외를 올린다.
    - `transport` 가 `FakeModem` 이면(`--fake`) 가상 노드를 config 의 `nodes` 에 맞춰 둔다.
    - store 는 부른 쪽이 닫는다. 모뎀 전송은 파이프라인이 닫는다.
    """
    stop = stop if stop is not None else asyncio.Event()
    link = link or link_run.main
    if isinstance(transport, FakeModem):
        if (cfg := store.get_config()) is not None:
            transport.apply_config(cfg)
        store.on_config_changed(transport.apply_config)
    pipeline = asyncio.create_task(Pipeline(store, transport).run(stop), name="modempi.pipeline")
    linker = asyncio.create_task(link(store), name="modempi.link")
    stopper = asyncio.create_task(stop.wait(), name="modempi.stop")
    unexpected: BaseException | None = None
    try:
        done, _ = await asyncio.wait(
            {pipeline, linker, stopper}, return_when=asyncio.FIRST_COMPLETED
        )
        if linker in done and linker.exception() is None:
            log.info("링크가 멈췄다(종료 신호) — 파이프라인도 멈춘다")
        if pipeline in done and pipeline.exception() is None and not stop.is_set():
            unexpected = RuntimeError("파이프라인이 stop 없이 끝났다")
    finally:
        stop.set()
        stopper.cancel()
        linker.cancel()  # 링크 쪽 stop 핸들은 link.run.main 안에 있다 — 취소로 멈춘다
        # 파이프라인은 stop 을 보고 스스로 정리한다(자식 취소·모뎀 닫기). 늦으면 끊는다.
        _, late = await asyncio.wait({pipeline}, timeout=SHUTDOWN_TIMEOUT_S)
        if late:
            log.error("파이프라인이 %s s 안에 멈추지 않았다 — 취소", SHUTDOWN_TIMEOUT_S)
            pipeline.cancel()
        await asyncio.gather(pipeline, linker, stopper, return_exceptions=True)
    for name, task in (("파이프라인", pipeline), ("링크", linker)):
        if not task.cancelled() and task.exception() is not None:
            log.error("%s 가 죽었다 — 서비스를 멈춘다: %r", name, task.exception())
            raise task.exception()
    if unexpected is not None:
        raise unexpected


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="modempi", description="모뎀Pi 서비스 (링크 + LoRa 파이프라인)"
    )
    p.add_argument(
        "--store",
        default=os.environ.get("MODEMPI_STORE"),
        help="JobStore SQLite 경로 (기본: env MODEMPI_STORE)",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--port", help="모뎀 시리얼 포트 (예 /dev/lora-modem)")
    g.add_argument("--fake", action="store_true", help="가짜 모뎀으로 기동 (하드웨어 없이)")
    args = p.parse_args(argv)
    if not args.store:
        p.error("--store 또는 env MODEMPI_STORE 가 필요하다")
    return args


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, sig), stop.set)
        except (NotImplementedError, AttributeError):  # Windows 개발 환경 — Ctrl+C 는 취소로 온다
            pass


async def open_best_effort(transport: SerialTransport) -> None:
    """한 번 열어 본다. 포트가 없어도 끝내지 않는다 — exit 하면 systemd 가 RestartSec 마다 재기동하며
    링크(메인Pi 연결)까지 끊겼다 붙는다. 이후는 `read_line` 의 재연결 루프가 맡고, 파이프라인은 모뎀의
    `ready` 가 올 때까지 기다린다."""
    try:
        await transport.open()
    except OSError as e:
        log.warning("모뎀 시리얼을 열지 못했다(%s) — 꽂힐 때까지 재연결을 시도한다", e)


async def _amain(args: argparse.Namespace) -> None:
    store = SqliteStore(args.store)
    transport: LineTransport = FakeModem() if args.fake else SerialTransport(args.port)
    try:
        if isinstance(transport, SerialTransport):
            await open_best_effort(transport)
        stop = asyncio.Event()
        _install_signal_handlers(stop)
        await serve(store, transport, stop=stop)
    finally:
        await transport.close()
        store.close()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # 링크는 env 에서 설정을 읽는다(LinkSettings). store 는 main 이 --store 로 연다 — 둘이 어긋나지 않게 맞춘다.
    env_store = os.environ.get("MODEMPI_STORE")
    if env_store and env_store != args.store:
        log.warning("MODEMPI_STORE=%s 대신 --store %s 를 쓴다", env_store, args.store)
    os.environ["MODEMPI_STORE"] = args.store
    # 누락이면 여기서 SystemExit — 태스크 안에서 나면 이벤트 루프를 깨고 나가 정리가 꼬인다.
    link_run.LinkSettings.from_env()
    try:
        asyncio.run(_amain(args))
    except KeyboardInterrupt:  # Windows 개발(신호 핸들러 없음)
        log.info("중단")
    except Exception:
        log.exception("모뎀Pi 서비스가 죽었다 — 재기동은 systemd(Restart=always) 몫")
        sys.exit(1)


if __name__ == "__main__":
    main()
