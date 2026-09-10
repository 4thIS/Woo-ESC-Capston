import json
from pathlib import Path

from lora_proto import proto as P
from lora_proto.codec import decode_frame, decode_payload, encode_frame, encode_payload
from tools import gen_vectors
from tools.gen_vectors import from_json, to_json

VEC = Path(__file__).resolve().parents[1] / "test_vectors.json"


def test_committed_vectors_match_generator():
    """드리프트 검사: codec 이나 생성기를 바꿨으면 `uv run python -m tools.gen_vectors` 로 재생성해 같이 커밋한다."""
    assert VEC.exists(), "test_vectors.json 없음 — uv run python -m tools.gen_vectors"
    assert json.loads(VEC.read_text(encoding="utf-8")) == gen_vectors.build()


def test_every_type_covered_at_least_once():
    types = {v["header"]["type"] for v in gen_vectors.build()["vectors"]}
    assert types == {int(t) for t in P.Type}


def test_each_vector_roundtrips_through_codec():
    for v in gen_vectors.build()["vectors"]:
        frame = bytes.fromhex(v["frame_hex"].replace(" ", ""))
        h, pb = decode_frame(frame)
        assert (h.type, h.bld, h.room, h.unit, h.txn, h.flags) == tuple(
            v["header"][k] for k in ("type", "bld", "room", "unit", "txn", "flags")
        ), v["name"]
        obj = decode_payload(h.type, pb)
        assert to_json(obj) == v["payload"], v["name"]
        assert encode_frame(h, encode_payload(from_json(h.type, v["payload"]))) == frame, v["name"]


def test_vectors_respect_size_limits():
    for v in gen_vectors.build()["vectors"]:
        assert len(bytes.fromhex(v["frame_hex"].replace(" ", ""))) <= P.MAX_FRAME, v["name"]
