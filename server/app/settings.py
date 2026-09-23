"""env → 설정. 테스트는 create_app(db_path)로 덮어쓴다. 필수 키가 없으면 기동 실패 (S4a §6)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _req(key: str) -> str:
    v = os.environ.get(key, "")
    if not v:
        raise RuntimeError(f"{key} 환경변수가 필요하다 (.env.example 참고)")
    return v


def _list(key: str) -> list[str]:
    return [x.strip() for x in os.environ.get(key, "").split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    db_path: str = field(default_factory=lambda: os.environ.get("SERVER_DB", "main.db"))
    status_hour_utc: int = field(
        default_factory=lambda: int(os.environ.get("STATUS_HOUR_UTC", "18"))
    )  # KST 03:00 (v2 §8.4)
    # ---- S4a 인증·메일·노출 면적 ----
    jwt_secret: str = field(default_factory=lambda: _req("JWT_SECRET"))
    jwt_ttl_h: int = field(default_factory=lambda: int(os.environ.get("JWT_TTL_H", "24")))
    student_web_url: str = field(default_factory=lambda: _req("STUDENT_WEB_URL").rstrip("/"))
    mail_backend: str = field(default_factory=lambda: os.environ.get("MAIL_BACKEND", "smtp"))
    smtp_user: str = field(default_factory=lambda: os.environ.get("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD", ""))
    mail_from: str = field(
        default_factory=lambda: os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "")
    )
    debug: bool = field(default_factory=lambda: os.environ.get("DEBUG", "0") == "1")
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS"))

    def __post_init__(self) -> None:
        if len(self.jwt_secret) < 32:
            raise RuntimeError(
                'JWT_SECRET 은 32자 이상 (python -c "import secrets;print(secrets.token_urlsafe(48))")'
            )
        if self.mail_backend == "smtp" and not (self.smtp_user and self.smtp_password):
            raise RuntimeError("MAIL_BACKEND=smtp 이면 SMTP_USER·SMTP_PASSWORD 가 필요하다")
        if self.mail_backend not in ("smtp", "console"):
            raise RuntimeError("MAIL_BACKEND 는 smtp | console")
