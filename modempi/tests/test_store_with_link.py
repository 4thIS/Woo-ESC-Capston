"""계약 ⑦ 통합 — 실제 LinkClient(wj) + FakeHub(계약 ⑥) 를 실물 SqliteStore 에 물린다.

링크 테스트는 MemoryStore 로 돈다. 여기서는 같은 링크 코드가 실물 store 와도 같은 의미로 도는지,
그리고 파이프라인 측 호출(pick_next·update·next_txn·put_uplink·set_meta)이 링크가 올리는 메시지로
이어지는지를 본다. 파이프라인 자체는 S6(cw-09) — 여기서는 그 호출만 흉내 낸다.
"""

import asyncio
import json

import pytest
from lora_proto import proto as P

from modempi.link.client import LinkClient
from modempi.store import SqliteStore

pytestmark = pytest.mark.anyio

JOB = {
    "job_id": 5,
    "bld": "E",
    "room": 301,
    "unit": 1,
    "type": "SLOT_SET",
    "payload": {
        "day": 1,
        "s_h": 9,
        "s_m": 0,
        "e_h": 10,
        "e_m": 0,
        "type": 1,
        "subject": "임베디드SW",
        "professor": "정필성",
    },
    "priority": 3,
    "new_ver": 1,
}


@pytest.fixture
def db(tmp_path):
    s = SqliteStore(str(tmp_path / "jobs.db"))
    yield s
    s.close()


async def _run(store, hub):
    c = LinkClient(store, url=hub.url, modem_id="m1", token="secret", upload_interval=0.05)
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    return c, task


async def _result_for(hub, job_id, timeout=2.0):
    async with asyncio.timeout(timeout):
        while True:
            for m in hub.received:
                if m.get("t") == "job_result" and m["job_id"] == job_id:
                    return m
            await asyncio.sleep(0.02)


async def test_link_and_pipeline_meet_only_through_sqlite_store(db, fake_hub):
    # 기동 전: 파이프라인이 모뎀 fw 를 기록했고, 지난 세션에서 못 올린 결과가 1건 있다
    db.set_meta("modem_fw", "0.3.0")
    db.put_job(
        job_id="1", bld="E", room=301, unit=2, type="CMD", payload="{}", priority=3, new_ver=None
    )
    db.update("1", state="acked", ack_status=0)
    configs = []
    db.on_config_changed(configs.append)

    fake_hub.jobs = [JOB, JOB]  # 같은 job_id 두 번
    c, task = await _run(db, fake_hub)
    try:
        hello = await fake_hub.wait_for("hello")
        assert hello["modem_fw"] == "0.3.0" and hello["pending_results"] == 1
        assert (await _result_for(fake_hub, 1))["state"] == "acked"  # 몰아 보내기
        await fake_hub.wait_for("job_accepted")

        # 링크 → store: config 저장 + 파이프라인 콜백, job 1회 저장
        assert db.get_config()["net_id"] == 0x4B and configs[0]["net_id"] == 0x4B
        j = db.get_job("5")
        assert (j.state, j.priority, j.new_ver) == ("received", 3, 1)
        assert json.loads(j.payload)["subject"] == "임베디드SW"

        # 파이프라인 흉내: 집고 → 보내고 → 결과 기록
        picked = db.pick_next()
        assert picked.job_id == "5"
        assert db.update("5", expect_state="received", state="sending") is True
        txn = db.next_txn(picked.bld, picked.room, picked.unit)
        db.update(
            "5",
            state="acked",
            attempts=1,
            txn=txn,
            ack_status=int(P.AckStatus.OK),
            rssi=-91,
            snr=6.5,
            node_vers={"sched": 1, "resv": 0, "exam": 0, "ident": 1},
            batt_mv=3950,
            layout=1,
            fw=3,
        )
        r = await _result_for(fake_hub, 5)
        assert (r["state"], r["txn"], r["attempts"], r["rssi"], r["snr"]) == (
            "acked",
            1,
            1,
            -91,
            6.5,
        )
        assert (r["sched_ver"], r["ident_ver"], r["batt_mv"], r["layout"], r["fw"]) == (
            1,
            1,
            3950,
            1,
            3,
        )
        assert isinstance(r["finished_at"], int)

        # time_now → TIME 행: 우선순위 0 으로 먼저 집히고, 메인에 보고하지 않는다
        await fake_hub.send({"t": "time_now", "request_status": False})
        db.put_job(
            job_id="6",
            bld="E",
            room=301,
            unit=1,
            type="CMD",
            payload="{}",
            priority=3,
            new_ver=None,
        )
        await fake_hub.send({"t": "ping"})
        await fake_hub.wait_for("pong")
        t = db.pick_next()
        assert t.type == "TIME" and t.uploaded == 1
        db.update(t.job_id, state="acked")

        # cancel → failed/cancelled 로 보고
        await fake_hub.send({"t": "cancel", "job_id": 6})
        r6 = await _result_for(fake_hub, 6)
        assert (r6["state"], r6["last_error"]) == ("failed", "cancelled")

        # 업링크
        db.put_uplink(
            {
                "kind": "STATUS",
                "bld": "E",
                "room": 301,
                "unit": 1,
                "mac": None,
                "batt_mv": 3900,
                "rssi": -95,
                "snr": 4.0,
            }
        )
        up = await fake_hub.wait_for("uplink")
        assert up["kind"] == "STATUS" and up["bld"] == "E"
        await asyncio.sleep(0.15)

        assert db.pending_results() == [] and db.pending_uplinks() == []
        results = [m["job_id"] for m in fake_hub.received if m["t"] == "job_result"]
        assert sorted(results) == [1, 5, 6]  # TIME 은 안 올라감, 중복 없음
    finally:
        await c.stop()
        await asyncio.wait_for(task, 3)
