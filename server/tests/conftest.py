import pytest
from fastapi.testclient import TestClient

from app.db import Base
from app.main import create_app


@pytest.fixture
def app(tmp_path):
    a = create_app(str(tmp_path / "t.db"))
    Base.metadata.create_all(a.state.engine)  # 테스트는 create_all, 실기는 alembic
    return a


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
