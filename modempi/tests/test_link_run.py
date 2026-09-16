import pytest

from modempi.link.client import LinkClient
from modempi.link.run import LinkSettings, build_client

from .fake_store import MemoryStore

ENV = {
    "MODEMPI_MAIN_URL": "ws://h/ws/modem",
    "MODEMPI_ID": "mjc-eng",
    "MODEMPI_TOKEN": "tok",
    "MODEMPI_STORE": "/var/lib/modempi/jobs.db",
}


def test_settings_from_env():
    s = LinkSettings.from_env(ENV)
    assert (s.url, s.modem_id, s.token, s.store_path) == (
        "ws://h/ws/modem",
        "mjc-eng",
        "tok",
        "/var/lib/modempi/jobs.db",
    )


def test_missing_env_lists_names():
    with pytest.raises(SystemExit) as e:
        LinkSettings.from_env({"MODEMPI_MAIN_URL": "ws://h"})
    assert (
        "MODEMPI_ID" in str(e.value)
        and "MODEMPI_TOKEN" in str(e.value)
        and "MODEMPI_STORE" in str(e.value)
    )


def test_build_client():
    c = build_client(LinkSettings.from_env(ENV), MemoryStore())
    assert isinstance(c, LinkClient) and c.modem_id == "mjc-eng" and c.url == "ws://h/ws/modem"
    assert c.agent_ver  # 패키지 버전 문자열
