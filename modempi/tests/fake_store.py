"""메모리 JobStore — 링크 테스트용. 계약 ⑦ 의미만 흉내 낸다 (S5 spec §4.2)."""

from __future__ import annotations

import time

from modempi.link.store_port import JobRow, UplinkRow

_ROW_FIELDS = (
    "state",
    "attempts",
    "txn",
    "ack_status",
    "ack_detail",
    "rssi",
    "snr",
    "node_vers",
    "batt_mv",
    "layout",
    "fw",
    "last_error",
    "finished_at",
)


class MemoryStore:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.uplinks: list[dict] = []
        self.config: dict | None = None
        self.meta: dict[str, str] = {}
        self._next_uplink = 1

    # ---- 링크가 쓰는 7 함수 + get_meta ----
    def put_job(
        self, *, job_id, bld, room, unit, type, payload, priority, new_ver, uploaded=0
    ) -> bool:
        if job_id in self.jobs:
            return False
        self.jobs[job_id] = {
            "job_id": job_id,
            "bld": bld,
            "room": room,
            "unit": unit,
            "type": type,
            "payload": payload,
            "priority": priority,
            "new_ver": new_ver,
            "state": "received",
            "attempts": 0,
            "txn": None,
            "ack_status": None,
            "ack_detail": None,
            "rssi": None,
            "snr": None,
            "node_vers": None,
            "batt_mv": None,
            "layout": None,
            "fw": None,
            "last_error": None,
            "received_at": time.time(),
            "finished_at": None,
            "uploaded": uploaded,
        }
        return True

    def cancel_job(self, job_id: str) -> bool:
        j = self.jobs.get(job_id)
        if j is None or j["state"] != "received":
            return False
        j["state"], j["finished_at"] = "cancelled", time.time()
        return True

    def pending_results(self, limit: int = 100) -> list[JobRow]:
        rows = [j for j in self.jobs.values() if j["finished_at"] is not None and not j["uploaded"]]
        rows.sort(key=lambda j: j["finished_at"])
        return [JobRow(job_id=j["job_id"], **{k: j[k] for k in _ROW_FIELDS}) for j in rows[:limit]]

    def mark_uploaded(self, job_ids: list[str]) -> None:
        for i in job_ids:
            if i in self.jobs:
                self.jobs[i]["uploaded"] = 1

    def set_config(self, config: dict) -> None:
        self.config = dict(config)

    def pending_uplinks(self, limit: int = 100) -> list[UplinkRow]:
        return [UplinkRow(u["id"], u["body"]) for u in self.uplinks if not u["uploaded"]][:limit]

    def mark_uplinks_uploaded(self, ids: list[int]) -> None:
        for u in self.uplinks:
            if u["id"] in ids:
                u["uploaded"] = 1

    def get_meta(self, key: str) -> str | None:
        return self.meta.get(key)

    # ---- 파이프라인 흉내 (테스트 전용) ----
    def set_meta(self, key: str, value: str) -> None:
        self.meta[key] = value

    def finish(self, job_id: str, **fields) -> None:
        j = self.jobs[job_id]
        j.update(fields)
        if j["finished_at"] is None:
            j["finished_at"] = time.time()

    def put_uplink(self, body: dict) -> int:
        i = self._next_uplink
        self._next_uplink += 1
        self.uplinks.append({"id": i, "body": body, "uploaded": 0})
        return i
