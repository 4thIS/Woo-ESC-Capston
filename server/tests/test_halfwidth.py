import datetime as dt

import pytest
from lora_proto import proto as P

from app.schemas import ResvIn, SlotIn, StudentResvIn, halfwidth

SPAN = {"s_h": 9, "s_m": 0, "e_h": 10, "e_m": 0, "type": 1}


def test_halfwidth_only_fullwidth_ascii_and_ideographic_space():
    """U+FF01–FF5E → U+0021–007E, U+3000 → 공백. 그 밖은 그대로 (#140)"""
    assert halfwidth("ＡＩ전자계산기구조") == "AI전자계산기구조"
    assert halfwidth("！～０９ａｚ（１）") == "!~09az(1)"
    assert halfwidth("웹　프로그래밍") == "웹 프로그래밍"
    # NFKC 와 다른 점 — 한글 낱자·원문자·로마 숫자·㈜·말줄임표는 건드리지 않는다
    keep = "강의실 ㅋㅋ ① Ⅱ ㈜ … ㎡ ｶ"
    assert halfwidth(keep) == keep


def test_span_schemas_store_halfwidth_and_measure_after():
    full = "Ａ" * (P.SUBJ_MAX // 3 + 1)  # 전각 그대로면 상한 초과
    s = SlotIn(day=1, subject=full, professor="ＬＥＥ", **SPAN)
    assert s.subject == "A" * len(full) and s.professor == "LEE"
    r = ResvIn(date=dt.date(2026, 11, 20), subject="ＡＩ", professor="　", **SPAN)
    assert r.subject == "AI" and r.professor == " "
    st = StudentResvIn(
        date=dt.date(2026, 11, 20), s_h=9, s_m=0, e_h=10, e_m=0, subject="ＡＩ 스터디"
    )
    assert st.subject == "AI 스터디"


def test_span_schemas_still_reject_over_limit():
    with pytest.raises(ValueError, match=f"> {P.SUBJ_MAX} B"):
        SlotIn(day=1, subject="a" * (P.SUBJ_MAX + 1), professor="", **SPAN)
