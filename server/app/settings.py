"""env → 설정. 테스트는 create_app(db_path)로 덮어쓴다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    db_path: str = field(default_factory=lambda: os.environ.get("SERVER_DB", "main.db"))
    status_hour_utc: int = field(
        default_factory=lambda: int(os.environ.get("STATUS_HOUR_UTC", "18"))
    )  # KST 03:00 (v2 §8.4)
