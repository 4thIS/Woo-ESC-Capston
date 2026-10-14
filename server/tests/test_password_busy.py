"""#51 — 로그인 폭주 때 scrypt 대기가 스레드풀을 쥐지 않게: 대기자 상한을 넘으면 기다리지 않고 바로 Busy(503)."""

import threading
import time

import pytest

from app.auth import password


def test_waiters_over_cap_get_busy_immediately_instead_of_holding_a_thread(monkeypatch):
    gate = threading.Event()
    real = password.hashlib.scrypt

    def slow(*a, **k):  # 슬롯을 쥔 채 멈춰 있는 scrypt
        gate.wait(5)
        return real(*a, **k)

    monkeypatch.setattr(password.hashlib, "scrypt", slow)
    stored = "scrypt$16$1$1$00$" + "00" * 32
    workers = [
        threading.Thread(target=password.verify, args=("pw", stored))
        for _ in range(2 + password.WAITERS_MAX)  # 슬롯 2 + 줄 상한만큼 채운다
    ]
    for t in workers:
        t.start()
    time.sleep(0.2)
    try:
        t0 = time.monotonic()
        with pytest.raises(password.Busy):
            password.verify("pw", stored)  # 줄이 꽉 찼다 — 기다리지 않는다
        assert time.monotonic() - t0 < 0.1
    finally:
        gate.set()
        for t in workers:
            t.join(5)
    assert password.verify("pw", stored) is False  # 풀리면 다시 정상(틀린 해시라 False)
