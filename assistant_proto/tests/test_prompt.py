from assistant_proto import (
    FIELD_ORDER,
    FIRST_PREFIX,
    INTENTS,
    SYSTEM_PROMPT,
    TYPE_LABELS,
    render_prefix,
)


def test_system_prompt_names_every_intent_field_and_type():
    for x in (*INTENTS, *FIELD_ORDER, *TYPE_LABELS):
        assert x in SYSTEM_PROMPT, x
    assert not SYSTEM_PROMPT.endswith("\n")


def test_render_prefix_matches_interface_example():
    p = render_prefix(
        "event.add",
        [
            ("강의실", "803"),
            ("날짜", "11/27(금)"),
            ("시각", "15:00~18:00"),
            ("유형", "특강"),
            ("이름", None),
        ],
        "특강 이름은 무엇인가요?",
    )
    assert p == (
        "상태: event.add | 강의실 803 | 날짜 11/27(금) | 시각 15:00~18:00 | 유형 특강 | 이름 ?\n"
        "질문: 특강 이름은 무엇인가요?\n"
        "관리자: "
    )
    assert FIRST_PREFIX == "관리자: " and p.endswith(FIRST_PREFIX)
