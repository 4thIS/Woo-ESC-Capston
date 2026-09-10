import pytest

from lora_proto import proto as P
from lora_proto.codec import (
    ExamSet,
    FileBegin,
    FileData,
    FileEnd,
    FrameError,
    ResvSet,
    SlotSet,
    build_file,
    crc16_ccitt,
    decode_payload,
    decode_records,
    encode_payload,
    encode_records,
)

S = [SlotSet(0, d, 9, 0, 10, 50, 1, f"과목{d}", "교수") for d in range(1, 6)]


def test_record_stream_layout():
    body = encode_records([S[0]])
    inner = encode_payload(S[0])[1:]  # NEW_VER 제거한 본문
    assert body == bytes([P.Type.SLOT_SET, len(inner)]) + inner
    assert decode_records(P.FileKind.SCHEDULE, body) == [S[0]]


def test_records_ignore_new_ver_field():
    assert encode_records([SlotSet(7, 1, 9, 0, 10, 0, 1, "a", "b")]) == encode_records(
        [SlotSet(0, 1, 9, 0, 10, 0, 1, "a", "b")]
    )


def test_mixed_kind_records_rejected():
    with pytest.raises(FrameError):
        encode_records([S[0], ExamSet(0, 1, 2026, 1, 1, 2026, 1, 2)])
    with pytest.raises(FrameError):
        decode_records(P.FileKind.EXAM, encode_records([S[0]]))


def test_build_file_chunks_and_crc():
    records = [
        SlotSet(0, 1 + i % 7, 9, 0, 10, 0, 1, "가" * 6 + "ab", "가" * 4) for i in range(30)
    ]  # 40 B × 30
    body = encode_records(records)
    parts = build_file(P.FileKind.SCHEDULE, records, new_ver=9)
    begin, *datas, end = parts
    assert begin == FileBegin(
        new_ver=9, kind=P.FileKind.SCHEDULE, total_len=len(body), n_chunks=len(datas)
    )
    assert all(len(d.data) <= P.FILE_CHUNK_MAX for d in datas)
    assert [d.seq for d in datas] == list(range(len(datas)))
    assert b"".join(d.data for d in datas) == body
    assert end == FileEnd(crc16=crc16_ccitt(body))
    assert len(datas) == -(-len(body) // P.FILE_CHUNK_MAX)


def test_file_payload_layouts():
    assert encode_payload(FileBegin(9, 1, 0x0123, 4)) == bytes([9, 1, 0x01, 0x23, 4])
    assert decode_payload(P.Type.FILE_BEGIN, bytes([9, 1, 0x01, 0x23, 4])) == FileBegin(
        9, 1, 0x123, 4
    )
    assert encode_payload(FileData(2, b"xyz")) == bytes([2]) + b"xyz"
    assert decode_payload(P.Type.FILE_DATA, bytes([2]) + b"xyz") == FileData(2, b"xyz")
    assert encode_payload(FileEnd(0x29B1)) == bytes([0x29, 0xB1])
    with pytest.raises(FrameError):
        encode_payload(FileData(0, bytes(201)))


def test_empty_file_is_one_begin_zero_data_one_end():
    parts = build_file(P.FileKind.RESV, [], new_ver=1)
    assert parts == [FileBegin(1, P.FileKind.RESV, 0, 0), FileEnd(crc16_ccitt(b""))]


def test_build_file_kind_must_match_records():
    with pytest.raises(FrameError):
        build_file(P.FileKind.RESV, S, new_ver=1)


def test_resv_and_exam_records_roundtrip():
    rs = [ResvSet(0, i, 2026, 11, 19, 13, 0, 15, 0, 6, "대관", "산학") for i in range(3)]
    assert decode_records(P.FileKind.RESV, encode_records(rs)) == rs
    es = [ExamSet(0, 1, 2026, 10, 20, 2026, 10, 24)]
    assert decode_records(P.FileKind.EXAM, encode_records(es)) == es
