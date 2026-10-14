"""빌드 직전(PlatformIO `extra_scripts = pre:`) src/fonts/*.bin(+.json) → lib/font_data/ C 배열 생성.

dh-04 plan D2 "(d) 빌드타임 생성". 표준 라이브러리만 쓴다(PlatformIO 파이썬에서 돈다).

- 커밋하는 원본은 src/fonts/<name>.bin(비트맵) + <name>.json(치수·코드포인트·진행폭)뿐이다.
  생성물 lib/font_data/ 는 .gitignore 대상이다(커밋 금지).
- lib/ 밑에 쓰므로 LDF 가 `#include "font_data.h"` 를 보고 자동 링크한다 — build_src_filter 수정 불필요.
- 정의는 font_data.cpp 한 곳에만 두고 헤더에는 extern 선언만 둔다. v1 처럼 배열을 헤더에 정의하면
  include 하는 .cpp 마다 조용히 복제돼 플래시를 몇 배로 먹는다(plan §3.3 실측).
- 입력이 안 바뀌었으면 파일을 다시 쓰지 않는다 → 수백 KB 배열을 매 빌드마다 재컴파일하지 않는다.
- 검증에 실패하면 빌드를 멈춘다: 비트맵 길이 ≠ 글자 수 × 글자당 바이트, 코드포인트 비오름차순,
  전체 폰트의 코드포인트가 lora_proto/lora_proto/charset.txt 와 다름(글자 목록 드리프트).

단독 실행도 된다: python firmware/tools/embed_fonts.py
"""

from __future__ import annotations

import json
import sys
from itertools import pairwise
from pathlib import Path

try:  # PlatformIO extra_scripts 로 돌 때는 SCons 가 Import·env 를 주입한다
    Import("env")
    FIRMWARE = Path(env.subst("$PROJECT_DIR"))
except NameError:  # 단독 실행
    FIRMWARE = Path(__file__).resolve().parents[1]

FONTS_DIR = FIRMWARE / "src" / "fonts"
OUT_DIR = FIRMWARE / "lib" / "font_data"
CHARSET_TXT = FIRMWARE.parent / "lora_proto" / "lora_proto" / "charset.txt"
HEADER = "// 자동 생성 — firmware/tools/embed_fonts.py 가 src/fonts/*.bin 에서 만든다. 고치지 말 것(커밋 금지).\n"


def fail(msg: str) -> None:
    sys.stderr.write(f"[embed_fonts] {msg}\n")
    sys.exit(1)


def read_charset() -> list[int]:
    cps = []
    for line in CHARSET_TXT.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            cps.append(int(line.split(" ", 1)[0], 16))
    return cps


def c_array(ctype: str, name: str, values, per_line: int, fmt: str) -> str:
    items = [fmt.format(v) for v in values]
    lines = [",".join(items[i : i + per_line]) for i in range(0, len(items), per_line)]
    return f"const {ctype} {name}[] = {{\n" + ",\n".join(lines) + "\n};\n"


def load_font(json_path: Path, charset: list[int] | None) -> tuple[dict, bytes]:
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    bitmaps = json_path.with_suffix(".bin").read_bytes()
    name = json_path.stem
    count, cps, adv = meta["count"], meta["codepoints"], meta["advances"]
    bpr, cell_h = meta["bytes_per_row"], meta["cell_h"]
    if bpr != (meta["cell_w"] + 7) // 8 or meta["bytes_per_glyph"] != cell_h * bpr:
        fail(f"{name}: 셀 치수 불일치")
    if len(bitmaps) != count * cell_h * bpr:
        fail(f"{name}.bin 크기 {len(bitmaps)} ≠ {count}자 × {cell_h * bpr} B")
    if len(cps) != count or len(adv) != count:
        fail(f"{name}: codepoints/advances 개수가 count({count})와 다름")
    if any(b <= a for a, b in pairwise(cps)) or cps[-1] > 0xFFFF:
        fail(f"{name}: 코드포인트가 오름차순·uint16 이 아님 — 이진탐색이 깨진다")
    if meta["charset"] == "charset.txt" and cps != charset:
        fail(
            f"{name}: 코드포인트가 charset.txt 와 다르다 — gen_fonts.py 로 다시 생성할 것"
        )
    return meta, bitmaps


def generate() -> None:
    charset = read_charset()
    fonts = [load_font(p, charset) for p in sorted(FONTS_DIR.glob("*.json"))]
    if not fonts:
        fail(f"{FONTS_DIR} 에 폰트 자산이 없다")

    h = [HEADER, "#pragma once\n", '#include "bitmap_font.h"\n', "\n"]
    cpp = [HEADER, '#include "font_data.h"\n', "\n", "namespace {\n"]
    defs = []
    for meta, bitmaps in fonts:
        sym, stem = meta["symbol"], meta["symbol"][1:]
        h.append(
            f"// {meta['family']} {meta['px']}px/{meta['weight']} — {meta['count']}자, "
            f"셀 {meta['cell_w']}x{meta['cell_h']}, {len(bitmaps):,} B\n"
        )
        h.append(f"extern const BitmapFont {sym};\n")
        cpp.append(c_array("uint16_t", f"{stem}Cp", meta["codepoints"], 16, "0x{:04x}"))
        cpp.append(c_array("uint8_t", f"{stem}Adv", meta["advances"], 32, "{}"))
        cpp.append(c_array("uint8_t", f"{stem}Bmp", bitmaps, 32, "0x{:02x}"))
        defs.append(
            f"const BitmapFont {sym} = {{{stem}Cp, {stem}Adv, {stem}Bmp, {meta['count']}, {meta['cell_w']}, "
            f"{meta['cell_h']}, {meta['bytes_per_row']}, {meta['baseline']}, {meta['origin_x']}}};\n"
        )
    cpp.append("}  // namespace\n\n")
    cpp.extend(defs)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fname, text in (("font_data.h", "".join(h)), ("font_data.cpp", "".join(cpp))):
        path = OUT_DIR / fname
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8", newline="\n")


generate()
