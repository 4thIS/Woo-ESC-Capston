# lora_proto — 공중 프로토콜 v2 단일 진실원

| 파일 | 역할 |
|---|---|
| `proto.h`, `radio_params.h` | **상수 원본** (C). 펌웨어가 include |
| `lora_proto/proto.py` | Python 미러. `tools/check_mirror.py`가 원본과 diff (CI) |
| `lora_proto/codec.py` | 프레임·페이로드 encode/decode, `build_file` |
| `tools/gen_vectors.py` → `test_vectors.json` | Python 이 만든 27개 프레임. `firmware/test/test_codec`(Unity)이 바이트 단위로 재검증 |
| `tools/gen_charset.py` → `lora_proto/charset.txt` | ESP노드 폰트 글자 목록 2,459자 (아래 절). `lora_proto/charset.py` 가 읽는다 |

## 글자 목록 (`charset.txt`, 이슈 #34)
- **무엇**: ESP노드 폰트가 그릴 수 있는 글자. KS X 1001 한글 2,350 + ASCII 인쇄 가능 95 + 추가 14(`Ⅰ`~`Ⅹ` `·` `–` `↑` `↓`).
- **누가 읽나**: 폰트 생성 도구(firmware, dh)는 파일을 바로, 서버 입력 검증(server, wj)은 `from lora_proto.charset import CHARSET, unsupported`. 형식은 한 줄에 `16진코드 글자`, 코드포인트 순.
- **목록 밖 글자**: 무선(UTF-8)으로는 가지만 노드가 못 그린다 → 서버가 CSV·폼 입력에서 막는다(계약 ⑤). 전각→반각 같은 정규화도 서버 몫.
- **바꾸는 법**: `tools/gen_charset.py` 규칙 수정 → `uv run python -m tools.gen_charset` → 아래 lockstep 과 같이 **단독 PR** 로 먼저 머지 → 폰트 재생성(dh)·서버 반영(wj). 파일을 손으로 고치면 드리프트 테스트가 막는다.

## 상수·규격을 바꿀 때 (lockstep)
1. `proto.h` / `radio_params.h` 수정 → `proto.py` 같은 값으로
2. `uv run python -m tools.check_mirror` → OK
3. `uv run python -m tools.gen_vectors` → `test_vectors.json` 갱신
4. `uv run pytest` 와 `cd ../firmware && pio test -e native` 둘 다 녹색
5. 이 다섯을 **한 PR** 로 먼저 머지한 뒤, 그 규격을 쓰는 펌웨어·modempi 코드 PR

## 개발
    uv sync && uv run pytest -q
