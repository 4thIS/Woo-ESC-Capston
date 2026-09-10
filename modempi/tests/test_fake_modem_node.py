import pytest
from lora_proto import codec as C
from lora_proto import proto as P

from .conftest import E, frame, hexs, send

pytestmark = pytest.mark.anyio


async def tx(modem, f, id_=1):
    r = await send(modem, {"op": "tx", "id": id_, "frame": hexs(f), "wake": True, "ack_ms": 100})
    assert r["status"] == "acked", r
    _, pb = C.decode_frame(bytes.fromhex(r["ack"].replace(" ", "")))
    return C.decode_payload(P.Type.ACK, pb)


async def test_same_txn_is_dup_without_reapply(modem):
    f = frame(P.Type.SLOT_DEL, C.SlotDel(3, 1, 9, 0), txn=9)
    a1 = await tx(modem, f)
    a2 = await tx(modem, f, 2)
    assert a1.status == P.AckStatus.OK and a2.status == P.AckStatus.DUP
    assert modem.nodes[(E, 301, 1)].sched_ver == 3


async def test_version_gap_is_reported_but_applied(modem):
    f = frame(P.Type.SLOT_DEL, C.SlotDel(5, 1, 9, 0), txn=10)  # 현재 2 → 5 (3, 4 유실)
    a = await tx(modem, f)
    assert a.status == P.AckStatus.GAP and a.sched_ver == 5
    assert modem.nodes[(E, 301, 1)].sched_ver == 5


async def test_version_rollover_255_to_1_is_continuous(modem):
    modem.nodes[(E, 301, 1)].sched_ver = 255
    a = await tx(modem, frame(P.Type.SLOT_DEL, C.SlotDel(1, 1, 9, 0), txn=11))
    assert a.status == P.AckStatus.OK and a.sched_ver == 1


async def test_kinds_have_independent_versions(modem):
    a = await tx(modem, frame(P.Type.RESV_DEL, C.ResvDel(1, 5), txn=12))
    assert a.status == P.AckStatus.OK and a.resv_ver == 1 and a.sched_ver == 2
    a = await tx(modem, frame(P.Type.EXAM_DEL, C.ExamDel(1, 5), txn=13))
    assert a.status == P.AckStatus.OK and a.exam_ver == 1


async def test_file_session_complete(modem):
    recs = [C.SlotSet(0, 1 + i % 7, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4) for i in range(12)]
    parts = C.build_file(P.FileKind.SCHEDULE, recs, new_ver=3)
    txn = 20
    for p in parts:
        t = C.type_of(p)
        a = await tx(modem, frame(t, p, txn=txn, flags=P.FLAG_ACK_REQ))
        txn += 1
    assert a.status == P.AckStatus.OK and a.sched_ver == 3
    assert len(modem.nodes[(E, 301, 1)].files[P.FileKind.SCHEDULE]) == len(recs)


async def test_file_session_missing_chunk(modem):
    recs = [C.SlotSet(0, 1 + i % 7, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4) for i in range(12)]
    begin, d0, d1, d2, end = C.build_file(P.FileKind.SCHEDULE, recs, new_ver=3)
    txn = 30
    for p in (begin, d0, d2):  # d1 누락
        await tx(modem, frame(C.type_of(p), p, txn=txn))
        txn += 1
    a = await tx(modem, frame(P.Type.FILE_END, end, txn=txn))
    assert a.status == P.AckStatus.FILE_MISSING and a.detail == 1
    assert modem.nodes[(E, 301, 1)].sched_ver == 2  # 미적용
    # 누락분 재송 후 END 재시도 → OK
    await tx(modem, frame(P.Type.FILE_DATA, d1, txn=txn + 1))
    a = await tx(modem, frame(P.Type.FILE_END, end, txn=txn + 2))
    assert a.status == P.AckStatus.OK and a.sched_ver == 3


async def test_set_room_provisions_unprovisioned_node(modem):
    mac = bytes.fromhex("a0b1c2d3e4f5")
    modem.add_unprovisioned(mac)
    f = frame(
        P.Type.SET_ROOM,
        C.SetRoom(1, mac, E, 302, 1),
        bld=P.BLD_UNPROVISIONED,
        room=0,
        unit=0,
        txn=1,
    )
    a = await tx(modem, f)
    assert (
        a.status == P.AckStatus.OK
        and (E, 302, 1) in modem.nodes
        and modem.nodes[(E, 302, 1)].ident_ver == 1
    )


async def test_cmd_request_status_emits_rx(modem):
    await tx(modem, frame(P.Type.CMD, C.Cmd(P.Cmd.REQUEST_STATUS), txn=40))
    import json

    r = json.loads(await modem.read_line())
    assert r["op"] == "rx"
    h, pb = C.decode_frame(bytes.fromhex(r["frame"].replace(" ", "")))
    assert h.type == P.Type.STATUS and C.decode_payload(P.Type.STATUS, pb).ack.sched_ver == 2
