import pytest

from app.assistant import rooms as R
from app.auth.scope import Scope
from tests.assistant_util import ALL, campus


def _resolve(app, expr, sc=ALL, **kw):
    with app.state.Session() as s:
        return R.resolve_room_expr(s, sc, expr, **kw)


def test_number_in_two_buildings_asks_room(app, school):
    ids = campus(app)
    got = _resolve(app, "803호")
    assert got == R.Ambiguous(
        "803호", ((f"room:{ids['E803']}", "공학관 803"), (f"room:{ids['H803']}", "인문관 803"))
    )


def test_building_admin_scope_narrows(app, school):
    ids = campus(app)
    only_e = Scope(1, frozenset({ids["E"]}), "b@mju.ac.kr")
    got = _resolve(app, "803", only_e)
    assert isinstance(got, R.Found) and [r.id for r in got.rooms] == [ids["E803"]]
    assert got.rooms[0].label == "공학관 803"
    assert isinstance(_resolve(app, "인문관 803", only_e), R.Missing)


@pytest.mark.parametrize(
    ("expr", "want"),
    [
        ("공학관 803", ["E803"]),
        ("E동 803", ["E803"]),
        ("801~803", ["E801", "E802", "E803"]),
        ("801호 ~ 803호", ["E801", "E802", "E803"]),
        ("공학관 8층 전체", ["E801", "E802", "E803", "E805"]),
        ("공학관", ["E301", "E801", "E802", "E803", "E805"]),
        ("인문관 2층", ["H201"]),
    ],
)
def test_found(app, school, expr, want):
    ids = campus(app)
    got = _resolve(app, expr)
    assert isinstance(got, R.Found) and [r.id for r in got.rooms] == [ids[k] for k in want]


def test_floor_across_buildings_asks_building(app, school):
    ids = campus(app)
    got = _resolve(app, "8층")
    assert got == R.Ambiguous(
        "8층", ((f"bld:{ids['E']}", "공학관 8층 (4개)"), (f"bld:{ids['H']}", "인문관 8층 (1개)"))
    )
    got = _resolve(app, "8층", only_building=ids["E"])
    assert [r.id for r in got.rooms] == [ids[k] for k in ("E801", "E802", "E803", "E805")]


@pytest.mark.parametrize("expr", ["999", "체육관 803", "어딘가", "Z동 803", "타교관 803"])
def test_missing(app, school, expr):
    campus(app)
    assert _resolve(app, expr) == R.Missing(expr)  # 다른 학교(Z) 방은 없는 것과 같다


@pytest.mark.parametrize(
    "expr", ["공학관803", "공학관 803", "공학관 803호", "공학관803호", "공 학 관 803"]
)
def test_whitespace_and_ho_variants_same_room(app, school, expr):
    ids = campus(app)
    got = _resolve(app, expr)
    assert isinstance(got, R.Found) and [r.id for r in got.rooms] == [ids["E803"]]


def _hall5(app):
    from app.domain.models import Building, Room

    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="5호관", bld="F")
        s.add(b)
        s.flush()
        rid = {}
        for n in (5, 201, 202):
            r = Room(building_id=b.id, room=n, units=1)
            s.add(r)
            s.flush()
            rid[n] = r.id
    return b.id, rid


@pytest.mark.parametrize("expr", ["5호관 201", "5호관201", "5호관 201호", "5 호관 201"])
def test_digit_building_name(app, school, expr):
    campus(app)
    _, rid = _hall5(app)
    got = _resolve(app, expr)
    assert isinstance(got, R.Found) and [r.id for r in got.rooms] == [rid[201]]


def test_digit_building_whole_range_floor(app, school):
    campus(app)
    _, rid = _hall5(app)
    got = _resolve(app, "5호관")
    assert [r.id for r in got.rooms] == [rid[5], rid[201], rid[202]]
    got = _resolve(app, "5호관 2층")
    assert [r.id for r in got.rooms] == [rid[201], rid[202]]
    got = _resolve(app, "5호관 201~202")
    assert [r.id for r in got.rooms] == [rid[201], rid[202]]
    got = _resolve(app, "5호관 5")  # 건물 5호관의 5호, 건물 이름의 5 가 아니다
    assert [r.id for r in got.rooms] == [rid[5]]


def _annex(app):
    from app.domain.models import Building, Room

    with app.state.Session() as s, s.begin():
        b = Building(school_id=1, name="공학관별관", bld="G")
        s.add(b)
        s.flush()
        r = Room(building_id=b.id, room=803, units=1)
        s.add(r)
        s.flush()
        return b.id, r.id


def test_exact_building_name_beats_prefix(app, school):
    ids = campus(app)
    _, annex803 = _annex(app)
    got = _resolve(app, "공학관 803")
    assert [r.id for r in got.rooms] == [ids["E803"]]
    got = _resolve(app, "공학관")
    assert {r.building_id for r in got.rooms} == {ids["E"]}
    got = _resolve(app, "공학관 8층")
    assert [r.id for r in got.rooms] == [ids[k] for k in ("E801", "E802", "E803", "E805")]
    got = _resolve(app, "공학관별관 803")
    assert [r.id for r in got.rooms] == [annex803]
    got = _resolve(app, "공학 803")  # 정확한 이름이 없으면 앞부분 일치
    assert isinstance(got, R.Ambiguous)


@pytest.mark.parametrize("expr", ["", "   ", "\t"])
def test_blank_is_missing(app, school, expr):
    campus(app)
    assert _resolve(app, expr) == R.Missing(expr)


def test_only_building_with_building_name(app, school):
    ids = campus(app)
    got = _resolve(app, "공학관 803", only_building=ids["E"])
    assert [r.id for r in got.rooms] == [ids["E803"]]
    assert _resolve(app, "인문관 803", only_building=ids["E"]) == R.Missing("인문관 803")
    got = _resolve(app, "공학관", only_building=ids["E"])
    assert len(got.rooms) == 5
