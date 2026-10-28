import pytest
from fastapi.testclient import TestClient

import app.auth.models
import app.domain.models
from app.auth import password, ratelimit, tokens
from app.auth.models import User
from app.db import Base
from app.domain.models import School
from app.lora_service import api
from app.lora_service.api import RoomInfo
from app.main import create_app
from app.settings import Settings


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Settings() 가 요구하는 env. 테스트마다 같은 값 — DEBUG 는 켠다(정적 페이지·/docs 테스트)."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-" + "x" * 32)  # 32자 이상 (S4a §2.3)
    monkeypatch.setenv("STUDENT_WEB_URL", "http://student.test")
    monkeypatch.setenv("MAIL_BACKEND", "console")
    monkeypatch.setenv("DEBUG", "1")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    ratelimit.reset()  # 테스트 간 카운터 격리
    # 저장 형식이 파라미터를 담으므로 낮춘 N 으로 만든 해시도 verify 된다 — 운영 값 형식은 test_auth_tokens 가 본다
    monkeypatch.setattr(password, "N", 2**10)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def app(tmp_path):
    a = create_app(str(tmp_path / "t.db"))
    Base.metadata.create_all(a.state.engine)  # 테스트는 create_all, 실기는 alembic
    return a


@pytest.fixture
def school(app):
    """학교 1(명지, E동 관리자 소속) + 학교 2(타교). 관리자 계정 둘."""
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                School(id=1, name="명지", net_id=75, email_domain="mju.ac.kr"),
                School(id=2, name="타교", net_id=76, email_domain="other.ac.kr"),
            ]
        )
        # 부모 먼저 — 안 하면 users 가 schools 보다 먼저 INSERT 돼 FK 위반(relationship() 없음, r2 🔴3)
        s.flush()
        s.add_all(
            [
                User(
                    email="admin@mju.ac.kr",
                    school_id=1,
                    role="admin",
                    status="active",
                    name="관리",
                    pw_hash=password.hash("adminpass1"),
                ),
                User(
                    email="admin@other.ac.kr",
                    school_id=2,
                    role="admin",
                    status="active",
                    name="타관리",
                    pw_hash=password.hash("adminpass1"),
                ),
            ]
        )
    return 1


def _hdr(app, email):
    with app.state.Session() as s:
        return {"Authorization": f"Bearer {tokens.jwt_encode(Settings(), s.get(User, email))}"}


@pytest.fixture
def admin_hdr(app, school):
    return _hdr(app, "admin@mju.ac.kr")


@pytest.fixture
def other_admin_hdr(app, school):
    return _hdr(app, "admin@other.ac.kr")


@pytest.fixture
def students(app, school):
    """학생 3명 (학교 1 에 2명, 학교 2 에 1명). school 과 분리 — 사용자 목록 단언을 건드리지 않게."""
    with app.state.Session() as s, s.begin():
        s.add_all(
            [
                User(
                    email="s1@mju.ac.kr",
                    school_id=1,
                    role="student",
                    status="active",
                    name="학생1",
                    student_no="S1",
                    pw_hash=password.hash("password1"),
                ),
                User(
                    email="s2@mju.ac.kr",
                    school_id=1,
                    role="student",
                    status="active",
                    name="학생2",
                    student_no="S2",
                    pw_hash=password.hash("password1"),
                ),
                User(
                    email="s3@other.ac.kr",
                    school_id=2,
                    role="student",
                    status="active",
                    name="타교생",
                    student_no="S3",
                    pw_hash=password.hash("password1"),
                ),
            ]
        )


@pytest.fixture
def student_hdr(app, students):
    return _hdr(app, "s1@mju.ac.kr")


@pytest.fixture
def other_student_hdr(app, students):
    return _hdr(app, "s2@mju.ac.kr")


@pytest.fixture
def student_hdr_school2(app, students):
    return _hdr(app, "s3@other.ac.kr")


@pytest.fixture
def client_raw(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(app, admin_hdr):
    """기존 테스트 호환: 학교 1 관리자 Bearer 를 자동으로 붙인다."""
    with TestClient(app, headers=admin_hdr) as c:
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
