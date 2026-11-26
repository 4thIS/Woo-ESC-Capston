"""/api/assistant/* (공통 부록 §4). 관리자 + 건물 범위(MgrScope). 핸들러는 요청 세션(_DB)에 쓰지 않고
request.app.state.Session 으로 직접 연다 — 미리보기가 다른 세션에서 쓰고 되돌리므로 SQLite 쓰기 잠금이 엇갈리지 않게."""

from __future__ import annotations

from assistant_proto import SCHEMA_VERSION
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.assistant import manifest, preview, service
from app.assistant import schemas as AS
from app.auth import ratelimit
from app.auth.deps import ManagerUser, MgrScope
from app.auth.scope import Scope
from app.domain import clock

router = APIRouter(prefix="/api/assistant", dependencies=[ManagerUser])
TURNS_PER_MIN = 60  # 관리자 이메일당 — 테스트가 바꿔 끼운다


@router.get("/model")
def model_info() -> dict:
    return manifest.load()


@router.post("/turns", response_model=AS.TurnOut)
def turns(body: AS.TurnIn, request: Request, sc: Scope = MgrScope):
    v = body.form.get("v") if body.form is not None else None
    if isinstance(v, int) and not isinstance(v, bool) and v != SCHEMA_VERSION:
        # 정수인데 다른 판일 때만 — v 가 없거나 이상하면 parse_form 이 보통의 오류 턴으로 답한다
        return JSONResponse({"detail": "schema_version"}, status_code=409)
    if not ratelimit.check(f"assistant:{sc.email}", limit=TURNS_PER_MIN):
        raise HTTPException(429, "잠시 후 다시 시도하세요")
    return service.handle_turn(request.app.state.Session, sc, body, clock.local_now())


@router.post("/previews/{preview_id}/apply")
def apply(preview_id: str, request: Request, sc: Scope = MgrScope):
    code, body = preview.apply_preview(request.app.state.Session, sc, preview_id, clock.local_now())
    return JSONResponse(jsonable_encoder(body), status_code=code)


@router.get("/changes", response_model=list[AS.ChangeOut])
def changes(request: Request, limit: int = Query(50, ge=1, le=200), sc: Scope = MgrScope):
    return service.list_changes(request.app.state.Session, sc, limit)
