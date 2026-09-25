"""요청 스코프 DB 세션. 라우터 공용 (domain·auth·lora)."""

from __future__ import annotations

from fastapi import Depends, Request


def get_db(request: Request):
    with request.app.state.Session() as s, s.begin():
        yield s


# scope="function": teardown(커밋·롤백)이 응답 전송 *전에* 돈다. 기본("request")은 응답을 보낸 뒤에
# 커밋해, 200 을 받은 클라이언트의 곧바른 재조회가 옛 상태를 읽었다(fastapi/routing.py function_stack).
# BackgroundTasks 는 응답 뒤에 돌므로 이제 커밋 뒤에 실행된다. B008 회피용 모듈 싱글턴 (ruff 권고).
_DB = Depends(get_db, scope="function")
