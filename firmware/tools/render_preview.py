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


def main() -> int:
    binary = sys.argv[1] if len(sys.argv) > 1 else str(FIRMWARE / ".pio" / "build" / "native_preview" / "program")
    OUT_DIR.mkdir(exist_ok=True)
    failures = 0
    for fixture in sorted(FIXTURES.glob("*.json")):
        out_png = OUT_DIR / f"{fixture.stem}.png"
        res = subprocess.run([binary, str(fixture), str(out_png)], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"FAIL {fixture.name}: {res.stderr.strip()}")
            failures += 1
        else:
            print(res.stdout.strip())
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
