"""모뎀과의 라인 전송 계약. 실물(modem.py, S6)은 pyserial-asyncio 위에, fake 는 메모리 큐 위에 구현한다."""

from __future__ import annotations

from typing import Protocol


class LineTransport(Protocol):
    async def write_line(self, line: str) -> None:
        """'\\n' 없는 한 줄(JSON)을 모뎀에 쓴다."""

    async def read_line(self) -> str:
        """모뎀이 올린 다음 한 줄을 돌려준다. 없으면 기다린다."""

    async def close(self) -> None: ...
