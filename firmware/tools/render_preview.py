"""firmware/test/fixtures/render/*.json 전체를 render_preview 실행파일로 돌려 PNG를 뽑는다.
실행 전 `pio run -e native_preview` (Task 6에서 확정)로 바이너리를 빌드해 둔다.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIRMWARE = Path(__file__).resolve().parents[1]
FIXTURES = FIRMWARE / "test" / "fixtures" / "render"
OUT_DIR = FIRMWARE / "test" / "fixtures" / "render" / "_out"
DEFAULT_BINARY = FIRMWARE / ".pio" / "build" / "native_preview" / "program"


def candidate_binaries(arg: str | None) -> list[Path]:
    """바이너리 후보 경로. PlatformIO 는 Windows 에서 program.exe 를 만들지만 plan·CI 명령은
    확장자 없이 `.pio/build/native_preview/program` 을 넘긴다 — 양쪽 다 받아준다."""
    raw = Path(arg) if arg else DEFAULT_BINARY
    if sys.platform == "win32" and raw.suffix != ".exe":
        return [raw, raw.with_suffix(".exe")]
    return [raw]


def main() -> int:
    candidates = candidate_binaries(sys.argv[1] if len(sys.argv) > 1 else None)
    binary = next((c for c in candidates if c.is_file()), None)
    if binary is None:
        print("render_preview 실행파일이 없습니다. 먼저 `pio run -e native_preview` 로 빌드하세요.", file=sys.stderr)
        for c in candidates:
            print(f"  찾아본 경로: {c}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    failures = 0
    for fixture in sorted(FIXTURES.glob("*.json")):
        out_png = OUT_DIR / f"{fixture.stem}.png"
        res = subprocess.run([str(binary), str(fixture), str(out_png)], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"FAIL {fixture.name}: {res.stderr.strip()}")
            failures += 1
        else:
            print(res.stdout.strip())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
