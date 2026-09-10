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
