"""stdlib scrypt. 저장 "scrypt$n$r$p$<salt hex>$<hash hex>" — 파라미터를 올려도 옛 해시 검증 가능 (S4a §2.3).
n=2**14 는 OWASP 권고보다 낮다 — Pi 메모리(2**17·r8 = 요청당 128 MB) 때문의 의도된 선택."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading

N, R, P = 2**14, 8, 1
_DUMMY = None  # lifespan 의 warm() 이 미리 만든다 — 재시작 뒤 첫 없는 주소 로그인만 느려지지 않게
# 동시 scrypt 2개 — 요청당 16 MB 라 스레드풀(40) 전부가 돌면 Pi 가 스왑·OOM. 초과 요청은 줄 서서 기다린다
# ponytail: 고정 2, 코어 수가 늘면 올린다
_SEM = threading.BoundedSemaphore(2)
SCRYPT_WAIT_S = 2.0  # 줄이 이보다 길면 Busy → 503. 무기한 대기는 스레드풀을 다 잡아 서버 전체가 멈춘다 (PR #42 🔴2)


class Busy(Exception):
    """scrypt 슬롯을 SCRYPT_WAIT_S 안에 못 얻었다 — main 의 핸들러가 503 으로 바꾼다."""


def _derive(pw: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    if not _SEM.acquire(timeout=SCRYPT_WAIT_S):
        raise Busy
    try:
        return hashlib.scrypt(
            pw.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=256 * 1024 * 1024
        )
    finally:
        _SEM.release()


def hash(pw: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${N}${R}${P}${salt.hex()}${_derive(pw, salt, N, R, P).hex()}"


def verify(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        return hmac.compare_digest(
            _derive(pw, bytes.fromhex(salt_hex), int(n), int(r), int(p)), bytes.fromhex(hash_hex)
        )
    except (ValueError, TypeError):
        return False


def warm() -> None:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash("dummy-password")


def dummy_verify(pw: str) -> None:
    """없는 사용자 로그인에도 같은 시간을 쓴다 — 응답 시간으로 가입 여부가 새지 않게 (S4a §3.4)."""
    warm()
    verify(pw, _DUMMY)
