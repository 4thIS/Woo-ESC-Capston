import asyncio
import json

import pytest

from modempi.link.client import LinkClient
from modempi.link.store_port import JobRow
from modempi.link.uploader import build_job_result

pytestmark = pytest.mark.anyio


def test_build_job_result_flattens_node_vers_and_int_job_id():
    row = JobRow(
        job_id="12",
        state="acked",
        attempts=2,
        txn=9,
        ack_status=0,
        ack_detail=0,
        rssi=-88,
        snr=7.5,
        node_vers=json.dumps({"sched": 3, "resv": 1, "exam": 0, "ident": 1}),
        batt_mv=3900,
        layout=1,
        fw=20,
        last_error=None,
        finished_at=1_800_000_123.4,
    )
    m = build_job_result(row)
    assert m == {
        "t": "job_result",
        "job_id": 12,
        "state": "acked",
        "ack_status": 0,
        "ack_detail": 0,
        "attempts": 2,
        "txn": 9,
        "rssi": -88,
        "snr": 7.5,
        "sched_ver": 3,
        "resv_ver": 1,
        "exam_ver": 0,
        "ident_ver": 1,
        "batt_mv": 3900,
        "layout": 1,
        "fw": 20,
        "last_error": None,
        "finished_at": 1_800_000_123,
    }


def test_build_job_result_cancelled_and_missing_vers():
    row = JobRow(job_id="3", state="cancelled", finished_at=1.0)
    m = build_job_result(row)
    assert m["state"] == "failed" and m["last_error"] == "cancelled"
    assert m["sched_ver"] is None and m["ident_ver"] is None


async def _run(store, hub, **kw):
    c = LinkClient(store, url=hub.url, modem_id="m1", token="secret", upload_interval=0.05, **kw)
    task = asyncio.create_task(c.run())
    await asyncio.wait_for(c.connected.wait(), 3)
    return c, task


async def test_results_and_uplinks_are_uploaded_and_marked(store, fake_hub):
    for i in ("1", "2", "3"):
        store.put_job(
            job_id=i, bld="E", room=301, unit=1, type="CMD", payload="{}", priority=3, new_ver=None
        )
    store.finish("1", state="acked", ack_status=0)
    store.cancel_job("2")
    store.put_uplink(
        {
            "kind": "HELLO",
            "bld": 0,
            "room": 0,
            "unit": 0,
            "mac": "aabbccddeeff",
            "fw": 20,
            "batt_mv": 4000,
            "rssi": -100,
            "snr": 3.0,
        }
    )
    c, task = await _run(store, fake_hub)
    hello = await fake_hub.wait_for("hello")
    assert hello["pending_results"] == 2
    await fake_hub.wait_for("uplink")
    await asyncio.sleep(0.1)
    results = [m for m in fake_hub.received if m["t"] == "job_result"]
    assert [(m["job_id"], m["state"], m["last_error"]) for m in results] == [
        (1, "acked", None),
        (2, "failed", "cancelled"),
    ]
    uplinks = [m for m in fake_hub.received if m["t"] == "uplink"]
    assert uplinks[0]["mac"] == "aabbccddeeff" and uplinks[0]["kind"] == "HELLO"
    # job_result 가 uplink 보다 먼저
    order = [m["t"] for m in fake_hub.received if m["t"] in ("job_result", "uplink")]
    assert order.index("uplink") > order.index("job_result")
    assert store.jobs["1"]["uploaded"] == 1 and store.jobs["2"]["uploaded"] == 1
    assert store.jobs["3"]["uploaded"] == 0 and store.uplinks[0]["uploaded"] == 1
    # 이후 새로 끝난 것도 올라간다
    store.finish("3", state="failed", last_error="no_ack")
    await asyncio.sleep(0.2)
    assert any(m["t"] == "job_result" and m["job_id"] == 3 for m in fake_hub.received)
    await c.stop()
    await asyncio.wait_for(task, 3)


async def test_non_numeric_job_id_row_is_marked_and_skipped(store, fake_hub, caplog):
    store.put_job(
        job_id="weird", bld="E", room=1, unit=1, type="CMD", payload="{}", priority=3, new_ver=None
    )
    store.finish("weird", state="acked")
    c, task = await _run(store, fake_hub)
    await asyncio.sleep(0.2)
    assert store.jobs["weird"]["uploaded"] == 1
    assert not any(m["t"] == "job_result" for m in fake_hub.received)
    assert "weird" in caplog.text
    await c.stop()
    await asyncio.wait_for(task, 3)
