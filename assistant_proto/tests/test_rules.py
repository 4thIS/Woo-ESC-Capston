from assistant_proto import INTENTS, render_prefix, rules


def test_primary_covers_every_actionable_intent():
    assert set(rules.PRIMARY) == set(INTENTS) - {"fill", "cancel", "unknown"}
    assert rules.PRIMARY["event.add"] == "set" and rules.PRIMARY["event.change"] == "set"
    assert rules.PRIMARY["event.remove"] == "target" and rules.PRIMARY["ask.node"] == "target"


def test_missing_event_add_order():
    m = rules.missing
    assert m("event.add", {}, {}) == "set.rooms"
    assert m("event.add", {}, {"rooms": ["803"]}) == "set.when"
    assert m("event.add", {}, {"rooms": ["803"], "when": "금"}) == "set.type"
    base = {"rooms": ["803"], "when": "금", "type": "특강"}
    assert m("event.add", {}, base) == "set.time"
    assert m("event.add", {}, {**base, "time": "3~6시"}) == "set.subject"
    assert m("event.add", {}, {**base, "time": "3~6시", "subject": "알고리즘 특강"}) is None
    # 휴강은 시각·과목 없이도 된다 — 서버가 그날 정규 수업에서 찾는다
    assert m("event.add", {}, {"rooms": ["803"], "when": "금", "type": "휴강"}) is None


def test_missing_change_and_remove():
    m = rules.missing
    assert m("event.change", {}, {}) == "target.rooms"
    assert m("event.change", {"rooms": ["803"]}, {}) == "target.when"
    assert m("event.change", {"rooms": ["803"], "when": "금"}, {}) == "target.time"
    assert m("event.change", {"rooms": ["803"], "when": "금", "type": "특강"}, {}) == "set.any"
    assert (
        m("event.change", {"rooms": ["803"], "when": "금", "type": "특강"}, {"time": "4시"}) is None
    )
    assert m("event.remove", {"rooms": ["803"], "when": "금", "subject": "x"}, {}) is None
    assert m("class.remove", {"rooms": ["803"]}, {}) == "target.when"
    assert m("class.add", {}, {"rooms": ["803"], "when": "월", "time": "9~12시"}) == "set.subject"
    assert m("exam.add", {}, {"rooms": ["803"]}) == "set.when"
    assert m("exam.change", {"rooms": ["803"]}, {}) == "set.when"
    assert m("exam.remove", {}, {}) == "target.rooms"
    assert m("request.approve", {}, {}) is None
    assert m("ask.free_rooms", {}, {}) == "target.when"
    assert m("ask.schedule", {}, {}) == "target.rooms"
    assert m("ask.node", {}, {}) == "target.rooms"
    assert m("ask.requests", {}, {}) is None


def test_question_texts():
    q = rules.question
    assert q("event.add", "set.subject", "특강") == "특강 이름은 무엇인가요?"
    assert q("class.add", "set.subject") == "과목명은 무엇인가요?"
    assert q("class.add", "set.when") == "무슨 요일인가요? (예: 월, 화목)"
    assert q("exam.add", "set.when") == "시험기간은 언제부터 언제까지인가요? (예: 12/15~12/19)"
    assert q("event.add", "set.when") == "날짜는 언제인가요? (예: 12/3, 이번 주 금요일)"
    assert q("event.add", "set.time") == "몇 시부터 몇 시까지인가요? (예: 15시~18시)"
    assert q("event.change", "set.any").startswith("무엇을 어떻게 바꿀까요?")


def test_class_target_time_question_has_no_event_wording():
    assert (
        rules.question("class.change", "target.time")
        == "몇 시 수업인가요? 과목 이름으로 알려 주셔도 됩니다."
    )
    assert (
        rules.question("class.remove", "target.time")
        == "몇 시 수업인가요? 과목 이름으로 알려 주셔도 됩니다."
    )
    assert (
        rules.question("event.change", "target.time")
        == "몇 시 일정인가요? 과목·행사 이름으로 알려 주셔도 됩니다."
    )


def test_state_items_example_and_change_labels():
    items = rules.state_items(
        "event.add",
        {},
        {"rooms": ["803"], "when": "이번 주 금요일", "time": "15시부터 18시까지", "type": "특강"},
        "set.subject",
    )
    assert items == [
        ("강의실", "803"),
        ("날짜", "이번 주 금요일"),
        ("시각", "15시부터 18시까지"),
        ("유형", "특강"),
        ("이름", None),
    ]
    items = rules.state_items(
        "event.change", {"rooms": ["803", "801"], "when": "금요일", "type": "특강"}, {}, "set.any"
    )
    assert items == [("대상 강의실", "803, 801"), ("대상 날짜", "금요일"), ("대상 유형", "특강")]
    assert rules.state_items("class.add", {}, {"rooms": ["801"], "when": "월"}, "set.subject")[
        -1
    ] == (
        "과목",
        None,
    )
    assert rules.state_items("exam.add", {}, {"rooms": ["801"]}, "set.when")[-1] == ("기간", None)
    # 칸이 아닌 빈 자리(선택지 고르기)는 상태에 넣지 않는다
    assert rules.state_items("event.remove", {"rooms": ["803"]}, {}, "target.pick") == [
        ("강의실", "803")
    ]


def test_render_with_state_items():
    p = render_prefix(
        "class.add",
        rules.state_items(
            "class.add", {}, {"rooms": ["801"], "when": "월", "time": "9시~12시"}, "set.subject"
        ),
        rules.question("class.add", "set.subject"),
    )
    assert (
        p
        == "상태: class.add | 강의실 801 | 요일 월 | 시각 9시~12시 | 과목 ?\n질문: 과목명은 무엇인가요?\n관리자: "
    )
