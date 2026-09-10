from tools import check_mirror


def test_headers_and_python_mirror_agree():
    assert check_mirror.diff() == []


def test_parser_reads_hex_and_float_defines(tmp_path):
    h = tmp_path / "x.h"
    h.write_text("#define A 0x4B // c\n#define B 922.5f\n#define C 9\n", encoding="utf-8")
    assert check_mirror.parse_defines(h) == {"A": 0x4B, "B": 922.5, "C": 9}


def test_parser_reads_enum_values(tmp_path):
    h = tmp_path / "y.h"
    h.write_text("enum { LP_T_A = 0x01, LP_T_B = 0x10, };\n", encoding="utf-8")
    assert check_mirror.parse_defines(h) == {"LP_T_A": 1, "LP_T_B": 16}


def test_parser_hex_ending_in_f_is_not_a_float_suffix(tmp_path):
    h = tmp_path / "z.h"
    h.write_text("#define A 0xFF\n#define B 0x4B\n#define C 125.0f\n", encoding="utf-8")
    assert check_mirror.parse_defines(h) == {"A": 0xFF, "B": 0x4B, "C": 125.0}


def test_diff_reports_python_only_scalar(monkeypatch):
    monkeypatch.setattr(check_mirror.P, "EXTRA_ONLY_IN_PY", 7, raising=False)
    assert any("EXTRA_ONLY_IN_PY" in p for p in check_mirror.diff())


def test_unparsed_detects_define_the_regex_cannot_read(tmp_path):
    h = tmp_path / "w.h"
    h.write_text("#define LP_X (1<<3)\n#define LP_Y 5\n", encoding="utf-8")
    lines = check_mirror.unparsed(h)
    assert len(lines) == 1
    assert "LP_X" in lines[0]


def test_unparsed_excludes_include_guard(tmp_path):
    h = tmp_path / "v.h"
    h.write_text("#ifndef LORA_PROTO_PROTO_H\n#define LORA_PROTO_PROTO_H\n", encoding="utf-8")
    assert check_mirror.unparsed(h) == []


def test_diff_style_report_contains_unparsed_marker(tmp_path):
    h = tmp_path / "w.h"
    h.write_text("#define LP_X (1<<3)\n", encoding="utf-8")
    lines = [f"{h.name}: 파싱 못한 #define: {line.strip()}" for line in check_mirror.unparsed(h)]
    assert any("파싱 못한" in line for line in lines)
