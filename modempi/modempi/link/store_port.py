"""계약 ⑦ JobStore 중 링크가 쓰는 인터페이스 (S5 spec §4.2). 실물은 modempi/store.py (cw-08).

동기 함수 — 루프에서 직접 호출한다 (S5 spec §9).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class JobRow:
    job_id: str
    state: str  # acked | failed | cancelled
    attempts: int = 0
    txn: int | None = None
    ack_status: int | None = None
    ack_detail: int | None = None
    rssi: int | None = None
    snr: float | None = None
    node_vers: str | None = None  # JSON {"sched","resv","exam","ident"}
    batt_mv: int | None = None
    layout: int | None = None
    fw: int | None = None
    last_error: str | None = None
    finished_at: float | None = None


@dataclass
class UplinkRow:
    id: int
    body: dict


class JobStore(Protocol):
    def put_job(
        self,
        *,
        job_id: str,
        bld: str,
        room: int,
        unit: int,
        type: str,
        payload: str,
        priority: int,
        new_ver: int | None,
        uploaded: int = 0,
    ) -> bool: ...
    def cancel_job(self, job_id: str) -> bool: ...
    def pending_results(self, limit: int = 100) -> list[JobRow]: ...
    def mark_uploaded(self, job_ids: list[str]) -> None: ...
    def set_config(self, config: dict) -> None: ...
    def pending_uplinks(self, limit: int = 100) -> list[UplinkRow]: ...
    def mark_uplinks_uploaded(self, ids: list[int]) -> None: ...
    def get_meta(self, key: str) -> str | None: ...  # 파이프라인이 set_meta 로 쓴 값 (modem_fw 등)
