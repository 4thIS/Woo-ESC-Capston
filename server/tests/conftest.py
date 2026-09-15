import pytest
from fastapi.testclient import TestClient

import app.domain.models
from app.db import Base
from app.lora_service import api
from app.lora_service.api import RoomInfo
from app.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def app(tmp_path):
    a = create_app(str(tmp_path / "t.db"))
    Base.metadata.create_all(a.state.engine)  # 테스트는 create_all, 실기는 alembic
    return a


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class FakeTopo:
    def __init__(self, rooms: dict[tuple[str, int], RoomInfo]):
        self.rooms = rooms

    def room(self, bld, room):
        return self.rooms.get((bld, room))

    def nodes(self, modem_id):
        return [
            (b, r, u)
            for (b, r), i in self.rooms.items()
            if i.modem_id == modem_id
            for u in range(1, i.units + 1)
        ]

    def net_id(self, modem_id):
        return 0x4B


class SpyHub:
    def __init__(self):
        self.notified, self.configs, self.cancels, self.time_calls = [], [], [], 0

    def notify(self, modem_id):
        self.notified.append(modem_id)

    def config_changed(self, modem_id):
        self.configs.append(modem_id)

    def time_now(self):
        self.time_calls += 1
        return 0

    def cancel(self, modem_id, job_id):
        self.cancels.append((modem_id, job_id))


@pytest.fixture
def topo():
    return FakeTopo(
        {
            ("E", 301): RoomInfo("m1", 2, 0x4B),
            ("E", 302): RoomInfo("m1", 1, 0x4B),
            ("E", 303): RoomInfo(None, 1, 0x4B),
        }
    )


@pytest.fixture
def hub():
    return SpyHub()


@pytest.fixture
def db(app, topo, hub):
    api.configure(app.state.Session)
    api.set_topology(topo)
    api.set_hub(hub)
    api.set_record_provider(lambda bld, room, kind: [])
    return app.state.Session


@pytest.fixture
def live(client, topo):
    """실제 Hub + FakeTopo. lifespan(client) 이 configure/set_hub 를 끝낸 뒤 topology 만 바꾼다."""
    api.set_topology(topo)
    api.set_record_provider(lambda bld, room, kind: [])
    return client.app.state.Session
