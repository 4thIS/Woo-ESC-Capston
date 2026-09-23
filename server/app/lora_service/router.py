"""lora_service HTTP/WS 라우트. 계약 ⑥ 엔드포인트 + 관리자 조회 (S4a §3.3 — 관리자 전용 + 학교 스코프)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, WebSocket
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import ratelimit, scope
from app.auth.deps import AdminUser
from app.auth.models import User
from app.deps import _DB
from app.lora_service import api
from app.lora_service.models import Modem, Outbox, PendingDevice

router = APIRouter()


@router.websocket("/ws/modem")
async def ws_modem(ws: WebSocket) -> None:
    await ws.app.state.hub.handle(ws)


rest = APIRouter(prefix="/api/lora", dependencies=[AdminUser])


@rest.get("/modems", response_model=list[S.ModemOut])
def list_modems(user: User = AdminUser):
    return [m for m in api.get_modems() if m.school_id == user.school_id]


@rest.post("/modems", response_model=S.TokenOut)
def register_modem(body: S.ModemIn, user: User = AdminUser, s: Session = _DB):
    # api 는 학교를 모른다 — 등록 직후 라우터가 채운다 (S4a §3.3)
    token = api.register_modem(body.modem_id)
    s.get(Modem, body.modem_id).school_id = user.school_id
    s.flush()  # 응답 전에 — 여기서 실패하면 모뎀이 school_id NULL 로 고립된다(복구는 CLI assign-modem)
    return {"modem_id": body.modem_id, "token": token}


@rest.post("/modems/{modem_id}/token", response_model=S.TokenOut)
def rotate(modem_id: str, user: User = AdminUser, s: Session = _DB):
    scope.get_scoped(s, Modem, modem_id, user.school_id)
    return {"modem_id": modem_id, "token": api.rotate_token(modem_id)}


@rest.get("/outbox", response_model=list[S.OutboxOut])
def outbox(
    state: str | None = None,
    bld: str | None = None,
    room: int | None = None,
    limit: int = 100,
    user: User = AdminUser,
    s: Session = _DB,
):
    keys = scope.room_keys(s, user.school_id)
    return [o for o in api.get_outbox(state, bld, room, limit) if (o.bld, o.room) in keys]


@rest.post("/outbox/{id}/cancel")
def cancel(id: int, user: User = AdminUser, s: Session = _DB):
    row = s.get(Outbox, id)
    if row is None or (row.bld, row.room) not in scope.room_keys(s, user.school_id):
        raise HTTPException(404, "취소할 수 없는 작업")
    if not api.cancel(id):
        raise HTTPException(404, "취소할 수 없는 작업")
    return {"ok": True}


@rest.get("/status", response_model=list[S.StatusOut])
def status(
    bld: str | None = None, room: int | None = None, user: User = AdminUser, s: Session = _DB
):
    keys = scope.room_keys(s, user.school_id)
    return [t for t in api.get_status(bld, room) if (t.bld, t.room) in keys]


@rest.get("/pending", response_model=list[S.PendingOut])
def pending(user: User = AdminUser, s: Session = _DB):
    mids = scope.modem_ids(s, user.school_id)
    return [p for p in api.get_pending_devices() if p.modem_id in mids]


@rest.post("/pending/{mac}/provision", response_model=S.Enqueued)
def provision(mac: str, body: S.ProvisionIn, user: User = AdminUser, s: Session = _DB):
    p = s.get(PendingDevice, mac)
    if p is None or p.modem_id not in scope.modem_ids(s, user.school_id):
        raise HTTPException(404, "pending 없음")
    if (body.bld, body.room) not in scope.room_keys(s, user.school_id):
        raise HTTPException(404, "rooms 없음")
    return {"outbox_ids": [api.provision(mac, body.bld, body.room, body.unit)]}


@rest.post("/time")
def time_now():
    """TIME 방송은 api 가 모든 모뎀에 보낸다(학교 개념 없음). 반복 호출로 전 노드를 깨우지 않게 전역 10분 1회 —
    TIME 은 원래 매시 1회라 수동 방송은 드물다 (S4a §3.3)."""
    if not ratelimit.check("lora:time", limit=1, window_s=600.0):
        raise HTTPException(429, "TIME 방송은 10분에 1회")
    return {"modems": api.request_time_broadcast()}


router.include_router(rest)
