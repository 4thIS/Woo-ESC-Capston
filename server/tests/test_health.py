def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_settings_read_env_at_instantiation(monkeypatch):
    from app.settings import Settings

    monkeypatch.setenv("STATUS_HOUR_UTC", "3")
    monkeypatch.setenv("QR_BASE_URL", "http://x")
    s = Settings()
    assert s.status_hour_utc == 3 and s.qr_base_url == "http://x"


def test_static_index_served(client):
    r = client.get("/static/index.html")
    assert r.status_code == 200 and "outbox" in r.text
