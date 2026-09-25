"""get_db 커밋 순서 — 응답이 나가는 시점에 쓰기가 이미 커밋돼 있어야 한다(쓰기 직후 조회가 옛 상태를 읽지 않게)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.models import User


def test_write_committed_before_response_start(app, admin_hdr):
    with app.state.Session() as s, s.begin():
        s.add(
            User(
                email="st@mju.ac.kr",
                school_id=1,
                role="student",
                status="disabled",
                name="학생",
                pw_hash="x",
            )
        )
    seen = []

    async def spy(scope, receive, send):
        async def send_spy(msg):
            if msg["type"] == "http.response.start" and scope["path"].endswith("/enable"):
                # 별도 세션 = 응답을 받은 클라이언트가 곧바로 던지는 조회
                with app.state.Session() as s2:
                    seen.append(s2.get(User, "st@mju.ac.kr").status)
            await send(msg)

        await app(scope, receive, send_spy)

    with TestClient(spy, headers=admin_hdr) as c:
        r = c.post("/api/admin/users/st@mju.ac.kr/enable")
    assert r.status_code == 200, r.text
    assert seen == ["active"]
