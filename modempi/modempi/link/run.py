"""env → LinkClient 기동. main.py(공용) 가 store 를 만들어 main(store) 를 태스크로 띄운다 (cw-08 뒤)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

from modempi.link.client import LinkClient
from modempi.link.store_port import JobStore

_KEYS = ("MODEMPI_MAIN_URL", "MODEMPI_ID", "MODEMPI_TOKEN", "MODEMPI_STORE")


@dataclass(frozen=True)
class LinkSettings:
    url: str
    modem_id: str
    token: str
    store_path: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> LinkSettings:
        missing = [k for k in _KEYS if not env.get(k)]
        if missing:
            raise SystemExit(f"MODEMPI_* 누락: {', '.join(missing)}")
        return cls(
            env["MODEMPI_MAIN_URL"], env["MODEMPI_ID"], env["MODEMPI_TOKEN"], env["MODEMPI_STORE"]
        )


def _agent_ver() -> str:
    try:
        return version("modempi")
    except PackageNotFoundError:
        return "0.0.0"


def build_client(settings: LinkSettings, store: JobStore) -> LinkClient:
    return LinkClient(
        store,
        url=settings.url,
        modem_id=settings.modem_id,
        token=settings.token,
        agent_ver=_agent_ver(),
    )


async def main(store: JobStore) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # 토큰이 DEBUG 프레임 로그에 찍히지 않게
    logging.getLogger("websockets").setLevel(logging.INFO)
    client = build_client(LinkSettings.from_env(), store)
    loop = asyncio.get_running_loop()
    for sig in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(
                getattr(signal, sig), lambda: asyncio.ensure_future(client.stop())
            )
        except (NotImplementedError, AttributeError):  # Windows 개발 환경
            pass
    await client.run()
