"""빌드 직전(PlatformIO `extra_scripts = pre:`) src/fonts/images/*.bin(+.json) → lib/image_data/ C 배열 생성.

embed_fonts.py(dh-04 plan D2)와 같은 방식 — 표준 라이브러리만 쓴다. 폰트와 별도 스크립트인 이유는
embed_fonts.py 의 `FONTS_DIR.glob("*.json")` 가 src/fonts/ 바로 아래만 보므로(비재귀), 이미지가
src/fonts/images/ 서브폴더에 있는 한 서로 부딪히지 않기 때문이다 — 폰트 메타(JSON 스키마: count·
codepoints·advances)와 이미지 메타(w·h·baseline)는 필드가 달라 한 로더로 같이 읽을 수 없다.

- 커밋하는 원본은 src/fonts/images/<name>.bin(비트맵) + <name>.json(치수·베이스라인)뿐이다.
  생성물 lib/image_data/ 는 .gitignore 대상이다(커밋 금지).
- lib/ 밑에 쓰므로 LDF 가 `#include "image_data.h"` 를 보고 자동 링크한다.
- 정의는 image_data.cpp 한 곳에만 두고 헤더에는 extern 선언만 둔다(font_data.py 와 같은 이유 —
  헤더에 배열을 정의하면 include 하는 .cpp 마다 복제된다).
- 입력이 안 바뀌었으면 파일을 다시 쓰지 않는다.
- 검증에 실패하면 빌드를 멈춘다: 비트맵 길이 ≠ w×h 기반 계산.

단독 실행도 된다: python firmware/tools/embed_images.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:  # PlatformIO extra_scripts 로 돌 때는 SCons 가 Import·env 를 주입한다
    Import("env")
    FIRMWARE = Path(env.subst("$PROJECT_DIR"))
except NameError:  # 단독 실행
    FIRMWARE = Path(__file__).resolve().parents[1]

IMAGES_DIR = FIRMWARE / "src" / "fonts" / "images"
OUT_DIR = FIRMWARE / "lib" / "image_data"
HEADER = "// 자동 생성 — firmware/tools/embed_images.py 가 src/fonts/images/*.bin 에서 만든다. 고치지 말 것(커밋 금지).\n"


def fail(msg: str) -> None:
    sys.stderr.write(f"[embed_images] {msg}\n")
    sys.exit(1)


def c_array(ctype: str, name: str, values, per_line: int, fmt: str) -> str:
    items = [fmt.format(v) for v in values]
    lines = [",".join(items[i : i + per_line]) for i in range(0, len(items), per_line)]
    return f"const {ctype} {name}[] = {{\n" + ",\n".join(lines) + "\n};\n"


def load_image(json_path: Path) -> tuple[dict, bytes]:
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    bitmap = json_path.with_suffix(".bin").read_bytes()
    name = json_path.stem
    w, h, bpr, baseline = meta["w"], meta["h"], meta["bytes_per_row"], meta["baseline"]
    if bpr != (w + 7) // 8:
        fail(f"{name}: bytes_per_row {bpr} != (w+7)//8 (w={w})")
    if len(bitmap) != h * bpr:
        fail(f"{name}.bin 크기 {len(bitmap)} != {h} 행 x {bpr} B")
    if not (0 <= baseline < 256):
        fail(f"{name}: baseline {baseline} 이 uint8 범위 밖")
    return meta, bitmap


def generate() -> None:
    if not IMAGES_DIR.exists():
        fail(f"{IMAGES_DIR} 없음")
    images = [load_image(p) for p in sorted(IMAGES_DIR.glob("*.json"))]
    if not images:
        fail(f"{IMAGES_DIR} 에 이미지 자산이 없다")

    h_lines = [HEADER, "#pragma once\n", '#include "bitmap_image.h"\n', "\n"]
    cpp_lines = [HEADER, '#include "image_data.h"\n', "\n", "namespace {\n"]
    defs = []
    for meta, bitmap in images:
        sym, stem = meta["symbol"], meta["symbol"][1:]
        h_lines.append(
            f"// {meta['text']!r} {meta['family']} {meta['px']}px/{meta['weight']} — "
            f"{meta['w']}x{meta['h']}, {len(bitmap):,} B\n"
        )
        h_lines.append(f"extern const BitmapImage {sym};\n")
        cpp_lines.append(c_array("uint8_t", f"{stem}Bmp", bitmap, 32, "0x{:02x}"))
        defs.append(
            f"const BitmapImage {sym} = {{{stem}Bmp, {meta['w']}, {meta['h']}, "
            f"{meta['bytes_per_row']}, {meta['baseline']}}};\n"
        )
    cpp_lines.append("}  // namespace\n\n")
    cpp_lines.extend(defs)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fname, text in (
        ("image_data.h", "".join(h_lines)),
        ("image_data.cpp", "".join(cpp_lines)),
    ):
        path = OUT_DIR / fname
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8", newline="\n")


generate()
