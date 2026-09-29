"""나눔고딕 TTF → 1비트 비트맵 폰트 자산(firmware/src/fonts/<name>.bin + <name>.json) 생성기.

오프라인 도구다. 빌드 때 돌지 않는다 — 빌드는 여기서 만든 .bin/.json 을 embed_fonts.py 가
C 배열로 바꿀 뿐이다. 글자 집합·크기·굵기를 바꿀 때만 다시 돌리고, 결과(.bin/.json)를 커밋한다.

필요 패키지: Pillow, fontTools (PlatformIO 파이썬에는 없다 — 임시 가상환경에서 실행).
    python firmware/tools/gen_fonts.py [--cache-dir DIR]

- 글자 집합의 단일 진실원은 lora_proto/lora_proto/charset.txt 다(이슈 #34). 순서(코드포인트 오름차순)가
  곧 글리프 저장 순서이고, 펌웨어는 그 순서를 이진탐색한다 — 그래서 frozenset 인 charset.py 가 아니라
  txt 를 직접 파싱한다. 작은 자산(16/32/62 px)의 글자도 반드시 charset.txt 안에 있어야 한다.
- 굵기·크기는 docs/design/screens/terminal-epaper.md "타입 — 6단계 고정" 표가 근거다.
- 각 크기를 **그 픽셀 크기에서 네이티브로** 래스터한다. 큰 크기로 그린 뒤 축소하지 않는다
  (축소는 임계값 정책만 바꿔도 획 위상이 21~97% 로 요동한다 — dh-04 plan §4.4).
  래스터 후 커버리지 128 이상을 잉크로 본다(이전 스파이크들과 같은 규칙).
- TTF 는 커밋하지 않는다. Google Fonts CSS2 API 에서 받아 캐시 폴더에만 둔다. 브라우저 User-Agent 를
  보내면 API 가 woff2 조각(unicode-range 분할)을 주므로 일부러 UA 를 보내지 않는다 → 단일 TTF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

FIRMWARE = Path(__file__).resolve().parents[1]
REPO = FIRMWARE.parent
CHARSET_TXT = REPO / "lora_proto" / "lora_proto" / "charset.txt"
OUT_DIR = FIRMWARE / "src" / "fonts"
INK_THRESHOLD = 128

PRIMARY = "Nanum Gothic"
# Google Fonts 나눔고딕(v3.020)에는 로마숫자 Ⅰ~Ⅹ(U+2160~2169) 글리프가 없다(400·700·800 모두,
# cmap 실측). charset.txt 는 이 10자를 "그릴 수 있는 글자"로 약속하므로, 주 폰트에 없는 글자만
# 같은 굵기의 Noto Sans KR(OFL) 글리프로 굽는다(dh-04 Task 3A Q1 (a) 채택 — ASCII I·V·X 를 이어
# 붙이는 안은 "VIII" 가 셀 폭을 키워 28px 자산이 +55% 라 기각). 대체된 코드포인트는
# JSON 의 fallback_codepoints 에 남는다. 라이선스 원문: src/fonts/NotoSansKR-OFL.txt
FALLBACK = "Noto Sans KR"

ASCII = "".join(chr(c) for c in range(0x20, 0x7F))

# (파일 이름, C 심벌, 픽셀 크기, 굵기, 글자 집합). 글자 집합 None = charset.txt 전체.
# 근거: terminal-epaper.md 타입표 + "필요한 자산" 표.
FONTS: list[tuple[str, str, int, int, str | None]] = [
    # 20/400 — 헤더 요일·상태 보조 문구·라벨·목록 과목
    ("nanum20r", "kNanum20Regular", 20, 400, None),
    # 20/700 — 오늘 목록 현재 진행 행(스펙 "과목 굵기 700")·layout 8 헤더 "미설정 단말"
    ("nanum20b", "kNanum20Bold", 20, 700, None),
    # 28/700 — 과목명·담당교수·강의시간 값 (28 px 는 스펙에서 700 으로만 쓰인다)
    ("nanum28b", "kNanum28Bold", 28, 700, None),
    # 16/400 — 푸터(E · 301 · U1)·목록 시각·"호"·"↑/↓ n개 더". 한글은 호·개·더 셋뿐(D5).
    ("nanum16r", "kNanum16Regular", 16, 400, ASCII + "·↑↓호개더"),
    # 32/800 — 헤더 호수(room u16) → 숫자만
    ("nanum32eb", "kNanum32ExtraBold", 32, 800, "0123456789"),
    # 62/800 — 다음 수업 시작 시각(13:00) · newTag("NEW-" + MAC 하위 2 B 대문자 16진)
    ("nanum62eb", "kNanum62ExtraBold", 62, 800, "0123456789:-ABCDEFNW"),
]


def read_charset() -> list[int]:
    """charset.txt 를 파일에 적힌 순서 그대로 읽는다. 오름차순·중복 없음을 여기서도 확인한다."""
    cps: list[int] = []
    for line in CHARSET_TXT.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        hex_code, _, glyph = line.partition(" ")
        cp = int(hex_code, 16)
        expected = " " if glyph == "(공백)" else glyph
        if chr(cp) != expected:
            sys.exit(f"charset.txt 줄 불일치: {line!r}")
        cps.append(cp)
    if cps != sorted(set(cps)):
        sys.exit("charset.txt 가 코드포인트 오름차순·중복 없음이 아니다")
    return cps


class FontSource:
    """Google Fonts 한 패밀리의 굵기별 TTF. 필요할 때만 받아 캐시에 둔다."""

    def __init__(self, family: str, cache_dir: Path) -> None:
        url = (
            "https://fonts.googleapis.com/css2?family="
            + family.replace(" ", "+")
            + ":wght@400;700;800"
        )
        with urllib.request.urlopen(url) as resp:
            css = resp.read().decode("utf-8")
        found = re.findall(r"font-weight:\s*(\d+);\s*src:\s*url\((\S+?\.ttf)\)", css)
        if len(found) != 3:
            sys.exit(
                f"{family}: CSS2 응답에서 TTF 3개를 찾지 못했다(다른 포맷을 줬을 수 있음):\n{css}"
            )
        self.family = family
        self.urls = {int(w): u for w, u in found}
        self.cache_dir = cache_dir

    def ttf(self, weight: int) -> Path:
        path = self.cache_dir / f"{self.family.replace(' ', '')}-{weight}.ttf"
        if not path.exists():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(self.urls[weight]) as resp:
                path.write_bytes(resp.read())
        return path


def render_ink(font: ImageFont.FreeTypeFont, ch: str, px: int) -> Image.Image:
    """펜 원점 (2px, 2px) 에 베이스라인을 두고 그린 뒤 임계값을 적용한 1비트 이미지."""
    img = Image.new("L", (px * 5, px * 4), 0)
    ImageDraw.Draw(img).text((px * 2, px * 2), ch, font=font, fill=255, anchor="ls")
    return img.point(lambda v: 255 if v >= INK_THRESHOLD else 0)


def rasterize(
    primary: Path, fallback: FontSource, weight: int, px: int, cps: list[int]
) -> dict:
    fonts = {}
    cmap_primary = TTFont(str(primary))["cmap"].getBestCmap()
    fallback_cps = [cp for cp in cps if cp != 0x20 and cp not in cmap_primary]
    fonts["primary"] = ImageFont.truetype(str(primary), px)
    if fallback_cps:
        fb_path = fallback.ttf(weight)
        cmap_fb = TTFont(str(fb_path))["cmap"].getBestCmap()
        still_missing = [f"U+{cp:04X}" for cp in fallback_cps if cp not in cmap_fb]
        if still_missing:
            sys.exit(
                f"{PRIMARY}·{FALLBACK} 어디에도 글리프가 없는 글자: {' '.join(still_missing)}"
            )
        fonts["fallback"] = ImageFont.truetype(str(fb_path), px)
    font_of = {cp: fonts["fallback" if cp in fallback_cps else "primary"] for cp in cps}

    # 셀 = 임계값 적용 후 실제 잉크 박스의 합집합(펜 원점·베이스라인 기준). 모든 글리프가 같은 셀을
    # 쓰므로 글리프 i 의 비트맵 위치가 i * 셀바이트 로 산술 계산된다(오프셋 표 불필요).
    inks = {cp: render_ink(font_of[cp], chr(cp), px) for cp in cps}
    boxes = [b for b in (img.getbbox() for img in inks.values()) if b]
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    origin_x, baseline = px * 2 - x0, px * 2 - y0
    cell_w, cell_h = x1 - x0, y1 - y0
    # origin_x 는 음수일 수 있다(모든 글리프의 왼쪽 여백이 양수면 셀이 펜 원점보다 오른쪽에서 시작) → int8.
    if not (
        -128 <= origin_x < 128 and 0 <= baseline < 256 and cell_w < 256 and cell_h < 256
    ):
        sys.exit(
            f"셀 치수가 uint8 범위 밖: {cell_w}x{cell_h} origin {origin_x} baseline {baseline}"
        )
    bpr = (cell_w + 7) // 8

    bitmaps = bytearray()
    advances: list[int] = []
    for cp in cps:
        pix = inks[cp].crop((x0, y0, x1, y1)).load()
        for y in range(cell_h):
            for bx in range(bpr):
                byte = 0
                for bit in range(8):
                    x = bx * 8 + bit
                    if x < cell_w and pix[x, y]:
                        byte |= 0x80 >> bit
                bitmaps.append(byte)
        adv = round(font_of[cp].getlength(chr(cp)))
        if not 0 < adv < 256:
            sys.exit(f"U+{cp:04X} 진행폭 {adv} 이 uint8 범위 밖")
        advances.append(adv)
    return {
        "cell_w": cell_w,
        "cell_h": cell_h,
        "bytes_per_row": bpr,
        "baseline": baseline,
        "origin_x": origin_x,
        "advances": advances,
        "fallback_codepoints": fallback_cps,
        "bitmaps": bytes(bitmaps),
    }


def write_json(path: Path, meta: dict) -> None:
    """배열(codepoints·advances)은 한 줄로 — 수천 줄짜리 diff 를 피한다."""
    items = list(meta.items())
    lines = ["{"]
    for i, (key, value) in enumerate(items):
        sep = "," if i < len(items) - 1 else ""
        lines.append(
            f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}{sep}"
        )
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "woo-esc-font-cache",
    )
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    charset = read_charset()
    charset_set = set(charset)
    primary = FontSource(PRIMARY, args.cache_dir)
    fallback = FontSource(FALLBACK, args.cache_dir)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, symbol, px, weight, chars in FONTS:
        if chars is None:
            cps = charset
        else:
            cps = sorted({ord(c) for c in chars})
            outside = [f"U+{cp:04X}" for cp in cps if cp not in charset_set]
            if outside:
                sys.exit(
                    f"{name}: charset.txt 밖의 글자 {outside} — 단일 진실원을 먼저 고쳐야 한다"
                )
        ttf = primary.ttf(weight)
        r = rasterize(ttf, fallback, weight, px, cps)
        bpg = r["cell_h"] * r["bytes_per_row"]
        if len(r["bitmaps"]) != len(cps) * bpg:
            sys.exit(f"{name}: 비트맵 길이 불일치")
        (OUT_DIR / f"{name}.bin").write_bytes(r["bitmaps"])
        meta = {
            "symbol": symbol,
            "family": PRIMARY,
            "weight": weight,
            "px": px,
            "charset": "charset.txt" if chars is None else "subset",
            "ttf_url": primary.urls[weight],
            "ttf_sha256": hashlib.sha256(ttf.read_bytes()).hexdigest(),
        }
        if r["fallback_codepoints"]:
            fb = fallback.ttf(weight)
            meta |= {
                "fallback_family": FALLBACK,
                "fallback_ttf_url": fallback.urls[weight],
                "fallback_ttf_sha256": hashlib.sha256(fb.read_bytes()).hexdigest(),
                "fallback_codepoints": r["fallback_codepoints"],
            }
        meta |= {
            "ink_threshold": INK_THRESHOLD,
            "cell_w": r["cell_w"],
            "cell_h": r["cell_h"],
            "bytes_per_row": r["bytes_per_row"],
            "baseline": r["baseline"],
            "origin_x": r["origin_x"],
            "count": len(cps),
            "bytes_per_glyph": bpg,
            "codepoints": cps,
            "advances": r["advances"],
        }
        write_json(OUT_DIR / f"{name}.json", meta)
        fb_note = (
            f", 대체 {len(r['fallback_codepoints'])}자"
            if r["fallback_codepoints"]
            else ""
        )
        print(
            f"{name}: {px}px/{weight} {len(cps)}자{fb_note} 셀 {r['cell_w']}x{r['cell_h']} "
            f"(원점 x{r['origin_x']}, 베이스라인 y{r['baseline']}, {bpg} B/자) → {len(r['bitmaps']):,} B"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
