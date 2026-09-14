import datetime as dt

from lora_proto import codec as C

from app.domain.models import Building, ExamPeriod, Reservation, Room, School, Slot
from app.domain.topology import DomainTopology, record_provider
from app.lora_service.api import RoomInfo
from app.lora_service.models import Modem


def _seed(Session):
    with Session() as s, s.begin():
        s.add(Modem(modem_id="mjc-eng", token_hash="x"))  # buildings.modem_id FK (app/db.py: FK ON)
        sch = School(name="명지", net_id=0x4B)
        s.add(sch)
        s.flush()
        b = Building(school_id=sch.id, name="공학관", bld="E", modem_id="mjc-eng")
        s.add(b)
        s.flush()
        r1 = Room(building_id=b.id, room=301, units=2)
        r2 = Room(building_id=b.id, room=302, units=1)
        s.add_all([r1, r2])
        s.flush()
        s.add(
            Slot(
                room_id=r1.id,
                day=1,
                s_h=9,
                s_m=0,
                e_h=10,
                e_m=50,
                type=1,
                subject="자료구조",
                professor="김",
            )
        )
        s.add(
            Reservation(
                id=7,
                room_id=r1.id,
                date=dt.date(2026, 9, 16),
                s_h=13,
                s_m=0,
                e_h=15,
                e_m=0,
                type=6,
                subject="대여",
                professor="",
            )
        )
        s.add(
            Reservation(
                id=8,
                room_id=r1.id,
                date=dt.date(2026, 10, 30),
                s_h=13,
                s_m=0,
                e_h=15,
                e_m=0,
                type=6,
                subject="먼예약",
                professor="",
            )
        )
        s.add(
            ExamPeriod(
                id=3,
                room_id=r1.id,
                date_start=dt.date(2026, 10, 19),
                date_end=dt.date(2026, 10, 23),
            )
        )
        return r1.id


def test_topology_resolves_room_nodes_net_id(app):
    _seed(app.state.Session)
    t = DomainTopology(app.state.Session)
    assert t.room("E", 301) == RoomInfo("mjc-eng", 2, 0x4B)
    assert t.room("E", 999) is None and t.room("Z", 301) is None
    assert sorted(t.nodes("mjc-eng")) == [("E", 301, 1), ("E", 301, 2), ("E", 302, 1)]
    assert t.nodes("nope") == [] and t.net_id("mjc-eng") == 0x4B and t.net_id("nope") is None


def test_record_provider_mirrors_codec_and_limits_resv_to_7_days(app):
    _seed(app.state.Session)
    rp = record_provider(app.state.Session, today=lambda: dt.date(2026, 9, 14))
    sched = rp("E", 301, "schedule")
    assert sched == [C.SlotSet(0, 1, 9, 0, 10, 50, 1, "자료구조", "김")]
    resv = rp("E", 301, "resv")
    assert [r.resv_id for r in resv] == [7]  # 10/30 은 7일 밖
    assert resv[0] == C.ResvSet(0, 7, 2026, 9, 16, 13, 0, 15, 0, 6, "대여", "")
    assert rp("E", 301, "exam") == [C.ExamSet(0, 3, 2026, 10, 19, 2026, 10, 23)]
    assert rp("E", 999, "schedule") == []
