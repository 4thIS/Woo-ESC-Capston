"""lora_service HTTP/WS 라우트. 계약 ⑥ 엔드포인트 + 관리자 조회 (Task 9 에서 REST 추가)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth.deps import AdminUser
from app.auth.models import User
from app.deps import _DB
from app.lora_service import api
from app.lora_service.models import Modem

router = APIRouter()


@router.websocket("/ws/modem")
async def ws_modem(ws: WebSocket) -> None:
    await ws.app.state.hub.handle(ws)


rest = APIRouter(prefix="/api/lora")


@rest.get("/modems", response_model=list[S.ModemOut])
def list_modems():
    return api.get_modems()


@rest.post("/modems", response_model=S.TokenOut)
def register_modem(body: S.ModemIn, user: User = AdminUser, s: Session = _DB):
    # api 는 학교를 모른다 — 등록 직후 라우터가 채운다 (S4a §3.3)
    token = api.register_modem(body.modem_id)
    s.get(Modem, body.modem_id).school_id = user.school_id
    s.flush()  # 응답 전에 — 여기서 실패하면 모뎀이 school_id NULL 로 고립된다(복구는 CLI assign-modem)
    return {"modem_id": body.modem_id, "token": token}


@rest.post("/modems/{modem_id}/token", response_model=S.TokenOut)
def rotate(modem_id: str):
    return {"modem_id": modem_id, "token": api.rotate_token(modem_id)}


@rest.get("/outbox", response_model=list[S.OutboxOut])
def outbox(
    state: str | None = None, bld: str | None = None, room: int | None = None, limit: int = 100
):
    return api.get_outbox(state, bld, room, limit)


@rest.post("/outbox/{id}/cancel")
def cancel(id: int):
    if not api.cancel(id):
        raise HTTPException(404, "취소할 수 없는 작업")
    return {"ok": True}


@rest.get("/status", response_model=list[S.StatusOut])
def status(bld: str | None = None, room: int | None = None):
    return api.get_status(bld, room)


@rest.get("/pending", response_model=list[S.PendingOut])
def pending():
    return api.get_pending_devices()


@rest.post("/pending/{mac}/provision", response_model=S.Enqueued)
def provision(mac: str, body: S.ProvisionIn):
    return {"outbox_ids": [api.provision(mac, body.bld, body.room, body.unit)]}


@rest.post("/time")
def time_now():
    return {"modems": api.request_time_broadcast()}


router.include_router(rest)
