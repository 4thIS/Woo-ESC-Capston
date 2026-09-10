# lora_proto — 공중 프로토콜 v2 단일 진실원

| 파일 | 역할 |
|---|---|
| `proto.h`, `radio_params.h` | **상수 원본** (C). 펌웨어가 include |
| `lora_proto/proto.py` | Python 미러. `tools/check_mirror.py`가 원본과 diff (CI) |
| `lora_proto/codec.py` | 프레임·페이로드 encode/decode, `build_file` |
| `tools/gen_vectors.py` → `test_vectors.json` | Python 이 만든 27개 프레임. `firmware/test/test_codec`(Unity)이 바이트 단위로 재검증 |

## 상수·규격을 바꿀 때 (lockstep)
1. `proto.h` / `radio_params.h` 수정 → `proto.py` 같은 값으로
2. `uv run python -m tools.check_mirror` → OK
3. `uv run python -m tools.gen_vectors` → `test_vectors.json` 갱신
4. `uv run pytest` 와 `cd ../firmware && pio test -e native` 둘 다 녹색
5. 이 다섯을 **한 PR** 로 먼저 머지한 뒤, 그 규격을 쓰는 펌웨어·modempi 코드 PR

## 개발
    uv sync && uv run pytest -q
