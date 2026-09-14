"""lora_service HTTP/WS 라우트. 계약 ⑥ 엔드포인트 + 관리자 조회 (Task 9 에서 REST 추가)."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

router = APIRouter()


@router.websocket("/ws/modem")
async def ws_modem(ws: WebSocket) -> None:
    await ws.app.state.hub.handle(ws)
