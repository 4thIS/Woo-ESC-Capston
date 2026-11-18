"""학교 · 건물 스코프 (S4a §3.3, #160). 범위 밖 리소스는 404 — 존재 자체를 숨긴다. lora_service 는 학교를 모른다.

최고 관리자(`admin`)는 학교 전체, 건물 관리자(`building_admin`)는 `user_buildings` 의 건물만 본다.
범위는 요청마다 DB 에서 읽는다 — 토큰에 굽지 않아 지정이 바뀌면 다음 요청부터 바로 맞다."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.auth.models import User, UserBuilding
from app.domain.models import Building, Room, School
from app.lora_service.models import Modem


@dataclass(frozen=True)
class Scope:
    school_id: int
    buildings: frozenset[int] | None = None  # None = 학교 전체(최고 관리자)
    email: str = ""

    def has(self, building_id: int) -> bool:
        return self.buildings is None or building_id in self.buildings


def of(s: Session, user: User) -> Scope:
    if user.role == "building_admin":
        ids = s.scalars(select(UserBuilding.building_id).where(UserBuilding.email == user.email))
        return Scope(user.school_id, frozenset(ids), user.email)
    return Scope(user.school_id, None, user.email)


def building_clause(sc: Scope):
    """Building 에 거는 WHERE — 학교 + (건물 관리자면) 맡은 건물."""
    c = Building.school_id == sc.school_id
    return c if sc.buildings is None else and_(c, Building.id.in_(sc.buildings))


def _school_of(s: Session, model, obj) -> int | None:
    if model is School:
        return obj.id
    if model is Building:
        return obj.school_id
    if model is Room:
        return s.get(Building, obj.building_id).school_id
    if model is Modem:
        return obj.school_id
    raise TypeError(model)


def _in_buildings(s: Session, model, obj, sc: Scope) -> bool:
    if sc.buildings is None or model is School:  # 학교는 읽기만 열린다 — 쓰기는 SuperUser 가 막는다
        return True
    if model is Building:
        return obj.id in sc.buildings
    if model is Room:
        return obj.building_id in sc.buildings
    if model is Modem:  # 모뎀은 건물을 따라간다 — 맡은 건물 중 하나라도 이 모뎀을 쓰면
        return obj.modem_id in modem_ids(s, sc)
    raise TypeError(model)


def get_scoped(s: Session, model, id_, sc: Scope):
    obj = s.get(model, id_)
    if (
        obj is None
        or _school_of(s, model, obj) != sc.school_id
        or not _in_buildings(s, model, obj, sc)
    ):
        raise HTTPException(404, f"{model.__tablename__} {id_} 없음")
    return obj


def building_ids(s: Session, sc: Scope) -> set[int]:
    return set(s.scalars(select(Building.id).where(building_clause(sc))))


def room_keys(s: Session, sc: Scope) -> set[tuple[str, int]]:
    """범위 안의 (bld, room) 전부 — outbox·terminal_status 필터용."""
    q = select(Building.bld, Room.room).join(Room, Room.building_id == Building.id)
    return set(s.execute(q.where(building_clause(sc))).all())


def modem_ids(s: Session, sc: Scope) -> set[str]:
    """학교의 모뎀. 건물 관리자는 맡은 건물이 쓰는 모뎀만 — 한 모뎀이 여러 건물을 맡아도 행 필터는
    room_keys 가 건물 단위로 다시 거른다."""
    school = set(s.scalars(select(Modem.modem_id).where(Modem.school_id == sc.school_id)))
    if sc.buildings is None:
        return school
    used = s.scalars(select(Building.modem_id).where(building_clause(sc)))
    return school & {m for m in used if m is not None}
