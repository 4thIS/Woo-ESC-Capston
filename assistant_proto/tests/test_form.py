import json
from dataclasses import replace

import jsonschema
import pytest

from assistant_proto import (
    FIELD_ORDER,
    INTENTS,
    SCHEMA_VERSION,
    TYPE_LABELS,
    Fields,
    FormError,
    canonical_json,
    form_to_dict,
    json_schema,
    parse_form,
    type_code,
)

GOOD = {
    "v": 1,
    "intent": "event.add",
    "target": {},
    "set": {
        "rooms": ["803"],
        "when": "이번 주 금요일",
        "time": "15시부터 18시까지",
        "type": "특강",
    },
}


def test_constants():
    assert SCHEMA_VERSION == 1
    assert len(INTENTS) == 18 and len(set(INTENTS)) == 18
    assert INTENTS[0] == "event.add" and INTENTS[-3:] == ("fill", "cancel", "unknown")
    assert TYPE_LABELS == ("수업", "시험", "휴강", "빈강의실", "특강", "대여")
    assert FIELD_ORDER == (
        "rooms",
        "when",
        "time",
        "type",
        "subject",
        "professor",
        "reason",
        "requester",
    )


def test_type_code():
    assert [type_code(x) for x in TYPE_LABELS] == [1, 2, 3, 4, 5, 6]
    with pytest.raises(ValueError):
        type_code("보강")


def test_parse_from_str_and_dict():
    f = parse_form(json.dumps(GOOD, ensure_ascii=False))
    assert f == parse_form(GOOD)
    assert f.intent == "event.add" and f.target == Fields()
    assert f.set.rooms == ("803",) and f.set.type == "특강" and f.set.subject is None


def test_form_to_dict_roundtrip():
    assert form_to_dict(parse_form(GOOD)) == GOOD


def test_canonical_json_orders_keys():
    shuffled = {
        "set": {
            "type": "특강",
            "time": "15시부터 18시까지",
            "when": "이번 주 금요일",
            "rooms": ["803"],
        },
        "target": {},
        "intent": "event.add",
        "v": 1,
    }
    want = (
        '{"v":1,"intent":"event.add","target":{},"set":{"rooms":["803"],'
        '"when":"이번 주 금요일","time":"15시부터 18시까지","type":"특강"}}'
    )
    assert canonical_json(shuffled) == want
    assert canonical_json(parse_form(GOOD)) == want


BAD = [
    "not json",
    [],
    {**GOOD, "v": 2},
    {**GOOD, "v": True},
    {**GOOD, "intent": "event.add2"},
    {k: v for k, v in GOOD.items() if k != "target"},
    {**GOOD, "extra": 1},
    {**GOOD, "set": {"room": ["803"]}},
    {**GOOD, "set": {"rooms": []}},
    {**GOOD, "set": {"rooms": ["8" * 21]}},
    {**GOOD, "set": {"rooms": "803"}},
    {**GOOD, "set": {"type": "보강"}},
    {**GOOD, "set": {"when": ""}},
    {**GOOD, "set": {"subject": None}},
    {**GOOD, "set": {"reason": "가" * 101}},
    {**GOOD, "target": []},
]


@pytest.mark.parametrize("bad", BAD)
def test_parse_rejects(bad):
    with pytest.raises(FormError):
        parse_form(bad)


def test_json_schema_matches_constants():
    sc = json_schema()
    assert sc["properties"]["v"] == {"const": 1}
    assert tuple(sc["properties"]["intent"]["enum"]) == INTENTS
    f = sc["$defs"]["fields"]
    assert tuple(f["properties"]) == FIELD_ORDER
    assert tuple(f["properties"]["type"]["enum"]) == TYPE_LABELS
    assert sc["additionalProperties"] is False and f["additionalProperties"] is False


def test_json_schema_accepts_good():
    assert not list(jsonschema.Draft202012Validator(json_schema()).iter_errors(GOOD))


@pytest.mark.parametrize("bad", [b for b in BAD if not isinstance(b, str)])
def test_json_schema_rejects_what_parser_rejects(bad):
    assert list(jsonschema.Draft202012Validator(json_schema()).iter_errors(bad)), bad


def test_canonical_json_validates_form_objects_too():
    form = parse_form(GOOD)
    bad = replace(form, set=replace(form.set, type="보강"))
    with pytest.raises(FormError):
        canonical_json(bad)
    with pytest.raises(FormError):
        canonical_json(replace(form, v=2))


def test_parse_deeply_nested_json_is_form_error():
    with pytest.raises(FormError):
        parse_form("[" * 100000)
