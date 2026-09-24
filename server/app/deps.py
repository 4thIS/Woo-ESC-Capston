"""요청 스코프 DB 세션. 라우터 공용 (domain·auth·lora)."""

from __future__ import annotations

from fastapi import Depends, Request


def get_db(request: Request):
    with request.app.state.Session() as s, s.begin():
        yield s


_DB = Depends(get_db)  # 참고: B008 회피용 모듈 싱글턴 (ruff 권고)
