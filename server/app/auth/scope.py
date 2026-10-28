"""학교 스코프 (S4a §3.3). 타 학교 리소스는 404 — 존재 자체를 숨긴다. lora_service 는 학교를 모른다."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Building, Room, School
from app.lora_service.models import Modem


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


def get_scoped(s: Session, model, id_, school_id: int):
    obj = s.get(model, id_)
    if obj is None or _school_of(s, model, obj) != school_id:
        raise HTTPException(404, f"{model.__tablename__} {id_} 없음")
    return obj


def room_keys(s: Session, school_id: int) -> set[tuple[str, int]]:
    """그 학교의 (bld, room) 전부 — outbox·terminal_status 필터용."""
    q = (
        select(Building.bld, Room.room)
        .join(Room, Room.building_id == Building.id)
        .where(Building.school_id == school_id)
    )
    return set(s.execute(q).all())


def modem_ids(s: Session, school_id: int) -> set[str]:
    return set(s.scalars(select(Modem.modem_id).where(Modem.school_id == school_id)))
