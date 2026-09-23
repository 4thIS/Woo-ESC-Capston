import pytest
from fastapi.testclient import TestClient

import app.domain.models  # noqa: F401
from app.db import Base
from app.main import create_app
from app.settings import Settings


def _fresh(path):
    """새 DB 로 앱을 만들고 테이블까지 — lifespan 의 sweep 이 빈 DB 를 조회하다 죽지 않게 (conftest `app` 과 같음)."""
    a = create_app(str(path))
    Base.metadata.create_all(a.state.engine)
    return a


def test_health_body_is_exactly_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"ok": True} and r.content == b'{"ok":true}'


def test_settings_read_env_at_instantiation(monkeypatch):
    monkeypatch.setenv("STATUS_HOUR_UTC", "3")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("JWT_TTL_H", "2")
    s = Settings()
    assert s.status_hour_utc == 3 and not hasattr(s, "qr_base_url")  # QR 폐기 (#16)
    assert s.jwt_secret.startswith("test-secret-") and s.debug is True
    assert s.cors_origins == ["http://a.test", "http://b.test"] and s.jwt_ttl_h == 2


def test_missing_or_short_jwt_secret_fails_fast(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Settings()
    monkeypatch.setenv("JWT_SECRET", "x" * 31)
    with pytest.raises(RuntimeError, match="32"):
        Settings()


def test_integrity_error_log_hides_parameters(app, caplog):
    import sqlalchemy.exc

    from app.domain.models import School

    with app.state.Session() as s, s.begin():
        s.add(School(id=1, name="a", net_id=75))
    with pytest.raises(sqlalchemy.exc.IntegrityError) as e, app.state.Session() as s, s.begin():
        s.add(School(id=2, name="secret-value", net_id=75))  # net_id UNIQUE 위반
    assert "secret-value" not in str(e.value)


def test_docs_and_static_only_in_debug(tmp_path, monkeypatch):
    with TestClient(_fresh(tmp_path / "a.db")) as c:
        assert c.get("/static/index.html").status_code == 200
        assert c.get("/docs").status_code == 200 and c.get("/openapi.json").status_code == 200
    monkeypatch.setenv("DEBUG", "0")
    with TestClient(_fresh(tmp_path / "b.db")) as c:
        for path in ("/static/index.html", "/docs", "/redoc", "/openapi.json"):
            assert c.get(path).status_code == 404, path
        assert c.get("/api/health").json() == {"ok": True}


def test_unhandled_exception_returns_fixed_500_body(app):
    @app.get("/_boom")
    def boom():
        raise RuntimeError("secret internals")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/_boom")
        assert r.status_code == 500 and r.json() == {"detail": "internal error"}
        assert "secret" not in r.text


def test_cors_blocked_by_default_and_allowed_when_listed(tmp_path, monkeypatch):
    with TestClient(_fresh(tmp_path / "a.db")) as c:
        r = c.get("/api/health", headers={"Origin": "http://evil.test"})
        assert "access-control-allow-origin" not in r.headers
    monkeypatch.setenv("CORS_ORIGINS", "http://admin.test")
    with TestClient(_fresh(tmp_path / "b.db")) as c:
        r = c.get("/api/health", headers={"Origin": "http://admin.test"})
        assert r.headers["access-control-allow-origin"] == "http://admin.test"
        r = c.get("/api/health", headers={"Origin": "http://evil.test"})
        assert "access-control-allow-origin" not in r.headers
