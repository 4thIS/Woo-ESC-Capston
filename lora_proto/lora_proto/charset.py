"""ESP노드 폰트가 그릴 수 있는 글자 목록 — charset.txt 를 읽는다 (이슈 #34).

서버는 노드로 가는 문자열(과목·교수·예약 이름 등)을 받을 때 `unsupported()` 로 검사한다.
무선은 UTF-8 이라 목록 밖 글자도 전송은 되지만 노드가 그리지 못한다. 전각→반각 같은 정규화는 서버 몫.
"""

from __future__ import annotations

from importlib.resources import files


def _load() -> frozenset[str]:
    text = files(__package__).joinpath("charset.txt").read_text(encoding="utf-8")
    # 첫 칸(16진 코드)이 원본이다. 둘째 칸 글자는 사람이 읽으라고 둔 것.
    return frozenset(
        chr(int(line.split(" ", 1)[0], 16))
        for line in text.splitlines()
        if line and not line.startswith("#")
    )


CHARSET: frozenset[str] = _load()


def unsupported(s: str) -> list[str]:
    """목록 밖 글자 — 나온 순서대로, 중복 없이. 비어 있으면 전부 그릴 수 있다."""
    return list(dict.fromkeys(c for c in s if c not in CHARSET))
