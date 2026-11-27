from assistant_proto import FIRST_PREFIX

from esc_ml.overlap import near_duplicates
from esc_ml.records import Example

FORM = {"v": 1, "intent": "cancel", "target": {}, "set": {}}


def ex(i, text):
    return Example(i, "test", "human", "2026-12-01T10:00:00+09:00", FIRST_PREFIX, text, FORM)


def test_exact_after_normalizing_is_flagged():
    got = near_duplicates(
        [ex("a", "803호 금요일 세미나 잡아줘!")], [ex("b", "803호금요일 세미나잡아줘")]
    )
    assert got == [("a", "b", 1.0)]


def test_short_phrases_are_exempt():
    assert near_duplicates([ex("a", "취소")], [ex("b", "취소")]) == []


def test_different_sentences_pass():
    got = near_duplicates(
        [ex("a", "공학관 803 다음 주 화요일 자료구조 휴강")],
        [ex("b", "801 시험기간 12/15~19 등록해줘")],
    )
    assert got == []
