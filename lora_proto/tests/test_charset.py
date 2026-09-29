from pathlib import Path

from lora_proto import charset
from lora_proto.charset import CHARSET, unsupported
from tools import gen_charset

TXT = Path(charset.__file__).with_name("charset.txt")


def test_committed_file_matches_generator():
    """드리프트 검사: 규칙을 바꿨으면 `uv run python -m tools.gen_charset` 로 재생성해 같이 커밋한다."""
    assert TXT.exists(), "charset.txt 없음 — uv run python -m tools.gen_charset"
    assert TXT.read_text(encoding="utf-8") == gen_charset.render()


def test_counts():
    hangul = [c for c in CHARSET if "가" <= c <= "힣"]
    ascii_ = [c for c in CHARSET if " " <= c <= "~"]
    assert len(hangul) == 2350  # KS X 1001 한글 전부, 전부 U+AC00–D7A3
    assert len(ascii_) == 95
    assert len(CHARSET) == 2459


def test_extra_14():
    extra = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ" + "·–↑↓"
    assert len(extra) == 14
    assert set(extra) <= CHARSET


def test_file_lines_are_code_then_glyph_in_order():
    codes = []
    for line in TXT.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        code, glyph = line.split(" ", 1)
        ch = chr(int(code, 16))
        assert glyph == ("(공백)" if ch == " " else ch), line
        codes.append(int(code, 16))
    assert codes == sorted(codes) and len(codes) == len(set(codes)) == len(CHARSET)


def test_unsupported():
    assert unsupported("자료구조Ⅲ") == []
    assert unsupported("임베디드 SW (A반) 1–2") == []
    assert unsupported("똠양꿍") == ["똠"]
    assert unsupported("Ａ") == ["Ａ"]  # 전각 → 반각 정규화는 서버 몫
    assert unsupported("똠똠Ａ뷁똠") == ["똠", "Ａ", "뷁"]  # 나온 순서, 중복 제거
    assert unsupported("") == []
