"""env → 설정. 테스트는 create_app(db_path)로 덮어쓴다."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.environ.get("SERVER_DB", "main.db")
    qr_base_url: str = os.environ.get("QR_BASE_URL", "")
    status_hour_utc: int = int(os.environ.get("STATUS_HOUR_UTC", "18"))  # KST 03:00 (v2 §8.4)
