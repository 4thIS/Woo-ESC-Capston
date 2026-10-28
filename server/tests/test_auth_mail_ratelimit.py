import smtplib

from app.auth import mailer, ratelimit
from app.settings import Settings


def test_templates_contain_link_with_token():
    st = Settings()
    subj, body = mailer.verify_mail(st, "TOK")
    assert "http://student.test/verify#token=TOK" in body and subj
    subj, body = mailer.reset_mail(st, "TOK2")
    assert "http://student.test/reset#token=TOK2" in body
    assert "승인" in mailer.decision_mail(True, None)[1]
    assert "사유: 학번 불일치" in mailer.decision_mail(False, "학번 불일치")[1]


def test_console_backend_prints(capsys):
    mailer.send(Settings(), "a@x.test", "제목", "본문", "verify")
    out = capsys.readouterr().out
    assert "a@x.test" in out and "본문" in out


def test_smtp_backend_uses_ssl_465_and_login(monkeypatch):
    monkeypatch.setenv("MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_USER", "me@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-pw")
    calls = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls["conn"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            calls["login"] = (u, p)

        def send_message(self, msg):
            calls["msg"] = msg

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    mailer.send(Settings(), "a@x.test", "제목", "본문", "verify")
    assert calls["conn"] == ("smtp.gmail.com", 465, 10) and calls["login"] == (
        "me@gmail.com",
        "app-pw",
    )
    m = calls["msg"]
    assert m["To"] == "a@x.test" and m["From"] == "me@gmail.com" and m["Subject"] == "제목"
    assert m.get_content().strip() == "본문"


def test_ratelimit_5_per_minute_then_resets(monkeypatch):
    ratelimit.reset()
    t = [1000.0]
    monkeypatch.setattr(ratelimit, "_now", lambda: t[0])
    assert all(ratelimit.check("a@x") for _ in range(5))
    assert not ratelimit.check("a@x")
    assert ratelimit.check("b@x")  # 키 별도
    t[0] += 61
    assert ratelimit.check("a@x")
    for i in range(1000):  # 창 지난 키는 정리된다 — dict 가 무한히 자라지 않게
        ratelimit.check(f"k{i}")
    t[0] += 61
    ratelimit.check("z")
    assert len(ratelimit._hits) <= 2


def test_ratelimit_sweep_keeps_long_windows(monkeypatch):
    """정리는 키마다 자기 창으로 — 하루 창 키가 1분 뒤 지워져 한도가 풀리면 안 된다 (r2 🟡, 실측 5분에 50건)."""
    ratelimit.reset()
    t = [1000.0]
    monkeypatch.setattr(ratelimit, "_now", lambda: t[0])
    assert ratelimit.check("resv:a", limit=1, window_s=86400.0)
    t[0] += 61
    ratelimit.check("other")  # sweep 유발
    assert not ratelimit.check("resv:a", limit=1, window_s=86400.0)
    t[0] += 86400
    assert ratelimit.check("resv:a", limit=1, window_s=86400.0)


def test_mail_caps_are_per_kind(monkeypatch, capsys):
    """가짜 가입이 verify 상한을 다 써도 재설정·승인 메일은 나간다 (r2 🟡)."""
    ratelimit.reset()
    monkeypatch.setattr(mailer, "MAIL_PER_HOUR", {"verify": 2, "reset": 1, "decision": 1})
    for i in range(3):
        mailer.send(Settings(), f"v{i}@x.test", "s", "b", "verify")
    mailer.send(Settings(), "r@x.test", "s", "b", "reset")
    mailer.send(Settings(), "d@x.test", "s", "b", "decision")
    out = capsys.readouterr().out
    assert "v0@x.test" in out and "v1@x.test" in out and "v2@x.test" not in out
    assert "r@x.test" in out and "d@x.test" in out


def test_mail_daily_cap_per_kind(monkeypatch, capsys):
    """Gmail 일일 한도(500) 보호 — 시간 상한만으론 하루 수천 통 (PR #42 🟡)."""
    ratelimit.reset()
    t = [1000.0]
    monkeypatch.setattr(ratelimit, "_now", lambda: t[0])
    monkeypatch.setattr(mailer, "MAIL_PER_DAY", {"verify": 2, "reset": 1, "decision": 1})
    for i in range(3):
        mailer.send(Settings(), f"v{i}@x.test", "s", "b", "verify")
    t[0] += 3601  # 시간 창은 지났지만 하루 창은 그대로
    mailer.send(Settings(), "v3@x.test", "s", "b", "verify")
    mailer.send(Settings(), "r@x.test", "s", "b", "reset")
    out = capsys.readouterr().out
    assert "v0@x.test" in out and "v1@x.test" in out
    assert "v2@x.test" not in out and "v3@x.test" not in out and "r@x.test" in out


def test_saturated_does_not_record(monkeypatch):
    ratelimit.reset()
    assert not ratelimit.saturated("k", limit=1, window_s=60.0)
    assert not ratelimit.saturated("k", limit=1, window_s=60.0)  # 세지 않는다
    assert ratelimit.check("k", limit=1, window_s=60.0)
    assert ratelimit.saturated("k", limit=1, window_s=60.0)


def test_console_backend_requires_debug(monkeypatch):
    """console 백엔드는 토큰을 stdout(journald)에 찍는다 — DEBUG=1 에서만 (PR #42 ⚪)."""
    import pytest

    monkeypatch.setenv("DEBUG", "0")
    with pytest.raises(RuntimeError, match="DEBUG=1"):
        Settings()
