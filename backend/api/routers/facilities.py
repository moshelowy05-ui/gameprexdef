import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_auth, get_session
from shared.db_models import FacilityORM, PlatformTypeORM

router = APIRouter()


class QueueProductionRequest(BaseModel):
    platform_type_key: str
    quantity: int
    priority: int = 5
    surge_mode: bool = False


@router.get("/{game_id}", response_model=list[dict])
async def list_facilities(
    game_id: str,
    faction: str | None = None,
    facility_type: str | None = None,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = select(FacilityORM).where(FacilityORM.session_id == uuid.UUID(game_id))
    if faction:
        stmt = stmt.where(FacilityORM.faction == faction)
    if facility_type:
        stmt = stmt.where(FacilityORM.facility_type == facility_type)
    result = await db.execute(stmt)
    return [_facility_to_dict(f) for f in result.scalars().all()]


@router.get("/{game_id}/{facility_id}")
async def get_facility(
    game_id: str,
    facility_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(FacilityORM).where(
            FacilityORM.session_id == uuid.UUID(game_id),
            FacilityORM.id == uuid.UUID(facility_id),
        )
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Facility not found")
    return _facility_to_dict(f)


@router.post("/{game_id}/{facility_id}/production")
async def queue_production(
    game_id: str,
    facility_id: str,
    req: QueueProductionRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(FacilityORM).where(
            FacilityORM.session_id == uuid.UUID(game_id),
            FacilityORM.id == uuid.UUID(facility_id),
        )
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Facility not found")

    ptype_result = await db.execute(
        select(PlatformTypeORM).where(
            PlatformTypeORM.type_key == req.platform_type_key
        )
    )
    ptype = ptype_result.scalar_one_or_none()
    ticks_per_unit = ptype.build_time_ticks if ptype else 72  # default 3 game-days

    order = {
        "id": str(uuid.uuid4()),
        "facility_id": facility_id,
        "type_key": req.platform_type_key,
        "platform_type_key": req.platform_type_key,
        "quantity": req.quantity,
        "quantity_remaining": req.quantity,
        "quantity_complete": 0,
        "ticks_per_unit": ticks_per_unit,
        "ticks_elapsed": 0,
        "priority": req.priority,
        "surge_mode": req.surge_mode,
        "resource_reserved": {},
    }
    queue = list(f.production_queue)
    queue.append(order)
    f.production_queue = sorted(queue, key=lambda o: o["priority"], reverse=True)
    return _facility_to_dict(f)


@router.delete("/{game_id}/{facility_id}/production/{order_id}")
async def cancel_production(
    game_id: str,
    facility_id: str,
    order_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(FacilityORM).where(
            FacilityORM.session_id == uuid.UUID(game_id),
            FacilityORM.id == uuid.UUID(facility_id),
        )
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=404, detail="Facility not found")
    f.production_queue = [o for o in f.production_queue if o["id"] != order_id]
    return _facility_to_dict(f)


@router.get("/{game_id}/platform-types/buildable", response_model=list[dict])
async def list_buildable_types(
    game_id: str,
    facility_type: str | None = None,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return platform types that can be queued for production."""
    stmt = select(PlatformTypeORM)
    if facility_type == "SHIPYARD":
        stmt = stmt.where(PlatformTypeORM.category.in_(["SHIP", "SUBMARINE"]))
    elif facility_type in ("AIRCRAFT_FACTORY",):
        stmt = stmt.where(PlatformTypeORM.category.in_(["AIRCRAFT", "UAV"]))
    result = await db.execute(stmt)
    return [
        {
            "type_key": pt.type_key,
            "platform_class": pt.category,
            "cruise_speed_knots": pt.cruise_speed_knots,
            "max_range_nm": pt.max_range_nm,
            "build_time_ticks": pt.build_time_ticks,
        }
        for pt in result.scalars().all()
    ]


def _facility_to_dict(f: FacilityORM) -> dict:
    return {
        "id": str(f.id),
        "facility_type": f.facility_type,
        "name": f.name,
        "faction": f.faction,
        "position": [f.position_lon, f.position_lat],
        "production_slots": f.production_slots,
        "health": f.health,
        "workforce": f.workforce,
        "power_state": f.power_state,
        "production_queue": f.production_queue,
        "storage": f.storage,
    }
