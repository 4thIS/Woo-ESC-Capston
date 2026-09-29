"""charset.txt 생성기 — ESP노드 폰트가 그릴 수 있는 글자 목록 (이슈 #34).
폰트 생성 도구(firmware, dh)와 서버 입력 검증(server, wj)이 같은 파일을 읽는다.
실행: uv run python -m tools.gen_charset  (lora_proto/ 에서)"""

from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "lora_proto" / "charset.txt"

# 한글: KS X 1001 완성형 2,350자 = cp949 첫 바이트 0xB0–0xC8 × 둘째 바이트 0xA1–0xFE
HANGUL = [bytes([hi, lo]).decode("cp949") for hi in range(0xB0, 0xC9) for lo in range(0xA1, 0xFF)]
# ASCII 인쇄 가능 95자 (0x20–0x7E)
ASCII = [chr(c) for c in range(0x20, 0x7F)]
# 추가 14자: 로마 숫자 Ⅰ~Ⅹ(학기·과목 번호), 가운뎃점, 강의시간 줄표, 목록 "n개 더" 화살표
EXTRA = [chr(c) for c in range(0x2160, 0x216A)] + ["·", "–", "↑", "↓"]

HEADER = """\
# lora_proto/charset.txt — ESP노드 폰트가 그릴 수 있는 글자 목록 (단일 진실원, 이슈 #34)
# 형식: 한 줄에 한 글자 "16진코드 글자", 코드포인트 순. 공백(0020)은 "(공백)" 으로 적는다. '#' 줄은 주석.
# 규칙: KS X 1001 한글 2,350 + ASCII 인쇄 가능 95 + 추가 14(Ⅰ~Ⅹ · – ↑ ↓) = {n}자
# 생성: cd lora_proto && uv run python -m tools.gen_charset  — 손으로 고치지 않는다(드리프트 테스트가 잡는다)
# 바꾸는 법: tools/gen_charset.py 규칙 수정 → 재생성 → lora_proto 단독 lockstep PR (README)
"""


def chars() -> list[str]:
    s = set(HANGUL) | set(ASCII) | set(EXTRA)
    assert len(s) == len(HANGUL) + len(ASCII) + len(EXTRA), "규칙끼리 겹침"
    return sorted(s)


def render() -> str:
    cs = chars()
    lines = [f"{ord(c):04X} {'(공백)' if c == ' ' else c}" for c in cs]
    return HEADER.format(n=f"{len(cs):,}") + "\n".join(lines) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(chars())} chars)")
    sys.exit(0)
