"""고정 문구(상태명·설정대기 제목·칩) → 1비트 비트맵 이미지 자산
(firmware/src/fonts/images/<name>.bin + <name>.json) 생성기.

오프라인 도구다. 빌드 때 돌지 않는다 — 빌드는 여기서 만든 .bin/.json 을 embed_images.py 가
C 배열로 바꿀 뿐이다. 문구·크기·굵기를 바꿀 때만 다시 돌리고, 결과(.bin/.json)를 커밋한다.

gen_fonts.py(dh-04 Task 3 Phase A)와 같은 파이프라인·같은 임계값(128)을 쓴다. 다른 점은
코드포인트별 글리프 표가 아니라 **문구 하나를 통째로 한 이미지로 굽는다**는 것 — 상태명·칩은
RenderModel 문자열이 아니라 고정 어휘라 조회가 필요 없다(docs/design/screens/terminal-epaper.md
"필요한 자산").

필요 패키지: Pillow (PlatformIO 파이썬에는 없다 — gen_fonts.py 가 쓰던 임시 가상환경 재사용).
    python firmware/tools/gen_images.py [--ttf-cache-dir DIR]

- 굵기·크기·자간은 docs/design/screens/terminal-epaper.md "타입 — 6단계 고정" 표가 근거다
  (78·62px 는 -0.03~-0.04em, 칩류 16px 는 +0.04em). 이 도구는 각 구간의 중간값 -0.035em 을 쓴다.
- 각 크기를 그 픽셀 크기에서 네이티브로 래스터한다(gen_fonts.py 와 같은 이유로 축소 금지).
- TTF 는 커밋하지 않는다. gen_fonts.py 가 이미 받아 둔 캐시(기본 %TEMP%/dh04-fonts)의
  NanumGothic-<weight>.ttf 를 그대로 쓴다 — 이 스크립트는 네트워크를 새로 열지 않는다
  (8종 문구 전부 주 폰트 cmap 안에 있음을 사전 확인했다 — Noto 대체 불필요).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIRMWARE = Path(__file__).resolve().parents[1]
OUT_DIR = FIRMWARE / "src" / "fonts" / "images"
INK_THRESHOLD = 128
FAMILY = "Nanum Gothic"

# (파일 이름, C 심벌, 픽셀 크기, 굵기, 문구). 근거: terminal-epaper.md 타입표 + "필요한 자산" 표.
IMAGES: list[tuple[str, str, int, int, str]] = [
    # 78px/800 — 상태명(layout 1~7 상태 띠). layout 8은 상태 띠를 쓰지 않고 "설정 대기"를
    # 62px 제목으로 그린다(스펙 타입표 62/800 "설정 대기 제목") — 78px 버전은 만들지 않는다.
    ("status_sueopjung", "kImgStatusSueopjung", 78, 800, "수업중"),
    ("status_swineunsigan", "kImgStatusSwineunsigan", 78, 800, "쉬는시간"),
    ("status_hyugang", "kImgStatusHyugang", 78, 800, "휴강"),
    ("status_binganguisil", "kImgStatusBinganguisil", 78, 800, "빈강의실"),
    ("status_siheomjung", "kImgStatusSiheomjung", 78, 800, "시험중"),
    ("status_teukgang", "kImgStatusTeukgang", 78, 800, "특강"),
    ("status_daeyeojung", "kImgStatusDaeyeojung", 78, 800, "대여중"),
    # 62px/800 — layout 8 본문 제목
    ("title_seoljeongdaegi", "kImgTitleSeoljeongdaegi", 62, 800, "설정 대기"),
    # 16px/700 칩류 — 글자 마스크만(칩 바탕 사각형·패딩은 Task4가 fillRect로 그린다)
    ("chip_oneul", "kImgChipOneul", 16, 700, "오늘"),
    ("chip_siheom", "kImgChipSiheom", 16, 700, "시험"),
    ("chip_hyugang", "kImgChipHyugang", 16, 700, "휴강"),
    ("chip_teukgang", "kImgChipTeukgang", 16, 700, "특강"),
    ("chip_daeyeo", "kImgChipDaeyeo", 16, 700, "대여"),
    ("chip_byeongyeong", "kImgChipByeongyeong", 16, 700, "변경"),
]

# px → 자간(em). 스펙 "자간: 78·62·32px는 -0.03~-0.04 em ... 칩류는 +0.04 em"의 중간값(78·62).
TRACKING_EM: dict[int, float] = {78: -0.035, 62: -0.035, 16: 0.04}


def render_phrase(
    font: ImageFont.FreeTypeFont, text: str, tracking_px: float, px: int
) -> dict:
    """펜 원점 (px*2, px*2) 에서 시작해 글자마다 자간을 더해가며 한 문구를 그리고,
    잉크 bbox 로 타이트 크롭한 1비트 데이터 + 치수 + 베이스라인을 반환한다.
    (gen_fonts.py 의 render_ink/rasterize 와 같은 좌표 규약 — 펜 원점 anchor="ls".)
    """
    canvas_w = px * (len(text) + 6)
    canvas_h = px * 4
    img = Image.new("L", (canvas_w, canvas_h), 0)
    draw = ImageDraw.Draw(img)
    origin_x = origin_y = float(px * 2)
    pen_x = origin_x
    for ch in text:
        draw.text((pen_x, origin_y), ch, font=font, fill=255, anchor="ls")
        pen_x += font.getlength(ch) + tracking_px
    ink = img.point(lambda v: 255 if v >= INK_THRESHOLD else 0)
    bbox = ink.getbbox()
    if not bbox:
        sys.exit(f"{text!r}: 잉크가 하나도 없다")
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    baseline = round(
        origin_y - y0
    )  # 이미지 윗변에서 베이스라인까지(px) — BitmapFont.baseline과 같은 규약
    if not (0 <= baseline < 256):
        sys.exit(f"{text!r}: 베이스라인 {baseline} 이 uint8 범위 밖")
    bpr = (w + 7) // 8

    pix = ink.crop((x0, y0, x1, y1)).load()
    bitmap = bytearray()
    for y in range(h):
        for bx in range(bpr):
            byte = 0
            for bit in range(8):
                x = bx * 8 + bit
                if x < w and pix[x, y]:
                    byte |= 0x80 >> bit
            bitmap.append(byte)
    return {
        "w": w,
        "h": h,
        "bytes_per_row": bpr,
        "baseline": baseline,
        "bitmap": bytes(bitmap),
    }


def write_json(path: Path, meta: dict) -> None:
    lines = ["{"]
    items = list(meta.items())
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
        "--ttf-cache-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "dh04-fonts",
        help="gen_fonts.py 가 받아 둔 NanumGothic-<weight>.ttf 캐시 폴더",
    )
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ttf_by_weight: dict[int, Path] = {}
    for _, _, _, weight, _ in IMAGES:
        if weight not in ttf_by_weight:
            path = args.ttf_cache_dir / f"NanumGothic-{weight}.ttf"
            if not path.exists():
                sys.exit(f"{path} 없음 — 먼저 gen_fonts.py 로 캐시를 채울 것")
            ttf_by_weight[weight] = path

    for name, symbol, px, weight, text in IMAGES:
        ttf = ttf_by_weight[weight]
        font = ImageFont.truetype(str(ttf), px)
        tracking_px = TRACKING_EM[px] * px
        r = render_phrase(font, text, tracking_px, px)
        (OUT_DIR / f"{name}.bin").write_bytes(r["bitmap"])
        meta = {
            "symbol": symbol,
            "text": text,
            "family": FAMILY,
            "weight": weight,
            "px": px,
            "tracking_em": TRACKING_EM[px],
            "ttf_sha256": hashlib.sha256(ttf.read_bytes()).hexdigest(),
            "ink_threshold": INK_THRESHOLD,
            "w": r["w"],
            "h": r["h"],
            "bytes_per_row": r["bytes_per_row"],
            "baseline": r["baseline"],
        }
        write_json(OUT_DIR / f"{name}.json", meta)
        print(
            f"{name}: {text!r} {px}px/{weight} {r['w']}x{r['h']} "
            f"(베이스라인 y{r['baseline']}) → {len(r['bitmap']):,} B"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
