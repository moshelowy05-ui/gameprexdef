import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_auth, get_session
from shared.db_models import PlatformORM, PlatformTypeORM
from shared.models import Platform
from shared.enums import PlatformClass, Faction, PlatformStatus
from shared.redis_client import get_redis
from sim_engine.models import OrderPriority, OrderType, OrderWaypoint, PlatformOrder
from sim_engine.order_queue import OrderQueue
from sim_engine.models import RKeys

router = APIRouter()


# ── Order request/response models ─────────────────────────────────────────────

class WaypointIn(BaseModel):
    lon: float
    lat: float
    action: str = "TRANSIT"
    hold_ticks: int = 0
    speed_override_knots: float | None = None


class SubmitOrderRequest(BaseModel):
    order_type: OrderType
    priority: OrderPriority = OrderPriority.ROUTINE
    waypoints: list[WaypointIn] = Field(default_factory=list)
    target_speed_knots: float | None = None
    rtb_facility_id: str | None = None
    mission_id: str | None = None


class OrderResponse(BaseModel):
    order_id: str
    game_id: str
    platform_id: str
    order_type: str
    priority: int
    queued: bool


@router.get("/types", response_model=list[dict])
async def list_platform_types(
    category: str | None = None,
    faction: str | None = None,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = select(PlatformTypeORM)
    if category:
        stmt = stmt.where(PlatformTypeORM.category == category)
    if faction:
        stmt = stmt.where(PlatformTypeORM.faction == faction)
    result = await db.execute(stmt.order_by(PlatformTypeORM.category, PlatformTypeORM.display_name))
    types = result.scalars().all()
    return [
        {
            "type_key": t.type_key,
            "display_name": t.display_name,
            "category": t.category,
            "faction": t.faction,
            "service": t.service,
            "max_speed_knots": t.max_speed_knots,
            "cruise_speed_knots": t.cruise_speed_knots,
            "max_range_nm": t.max_range_nm,
            "crew_requirement": t.crew_requirement,
            "build_time_ticks": t.build_time_ticks,
            "build_cost": t.build_cost,
            "hardpoints": t.hardpoints,
            "sensor_suite": t.sensor_suite,
            "signature": t.signature,
            "description": t.description,
        }
        for t in types
    ]


@router.get("/types/{type_key}")
async def get_platform_type(
    type_key: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(PlatformTypeORM).where(PlatformTypeORM.type_key == type_key)
    )
    pt = result.scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=404, detail="Platform type not found")
    return {
        "type_key": pt.type_key,
        "display_name": pt.display_name,
        "category": pt.category,
        "faction": pt.faction,
        "service": pt.service,
        "max_speed_knots": pt.max_speed_knots,
        "cruise_speed_knots": pt.cruise_speed_knots,
        "max_range_nm": pt.max_range_nm,
        "fuel_capacity_lbs": pt.fuel_capacity_lbs,
        "fuel_burn_rate_per_tick": pt.fuel_burn_rate_per_tick,
        "crew_requirement": pt.crew_requirement,
        "build_time_ticks": pt.build_time_ticks,
        "maintenance_interval_ticks": pt.maintenance_interval_ticks,
        "build_cost": pt.build_cost,
        "hardpoints": pt.hardpoints,
        "sensor_suite": pt.sensor_suite,
        "signature": pt.signature,
        "upgrade_paths": pt.upgrade_paths,
        "description": pt.description,
    }


@router.get("/{game_id}", response_model=list[dict])
async def list_platforms(
    game_id: str,
    faction: str | None = None,
    status: str | None = None,
    platform_class: str | None = None,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = select(PlatformORM).where(PlatformORM.session_id == uuid.UUID(game_id))
    if faction:
        stmt = stmt.where(PlatformORM.faction == faction)
    if status:
        stmt = stmt.where(PlatformORM.status == status)
    if platform_class:
        stmt = stmt.where(PlatformORM.platform_class == platform_class)
    result = await db.execute(stmt)
    platforms = result.scalars().all()
    return [_platform_to_dict(p) for p in platforms]


@router.get("/{game_id}/{platform_id}")
async def get_platform(
    game_id: str,
    platform_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(PlatformORM).where(
            PlatformORM.session_id == uuid.UUID(game_id),
            PlatformORM.id == uuid.UUID(platform_id),
        )
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Platform not found")
    return _platform_to_dict(p)


@router.post("/{game_id}/{platform_id}/orders", response_model=OrderResponse)
async def submit_order(
    game_id: str,
    platform_id: str,
    body: SubmitOrderRequest,
    request: Request,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> OrderResponse:
    """Submit a movement or control order for a platform."""
    # Verify platform belongs to this game
    result = await db.execute(
        select(PlatformORM).where(
            PlatformORM.session_id == uuid.UUID(game_id),
            PlatformORM.id == uuid.UUID(platform_id),
        )
    )
    platform = result.scalar_one_or_none()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    # Get current tick from Redis (fast path) or default to 0
    redis = get_redis()
    raw_tick = await redis.get(RKeys.game_tick(game_id))
    current_tick = int(raw_tick) if raw_tick is not None else 0

    order = PlatformOrder(
        id=str(uuid.uuid4()),
        game_id=game_id,
        platform_id=platform_id,
        order_type=body.order_type,
        priority=body.priority,
        submission_tick=current_tick,
        waypoints=[
            OrderWaypoint(
                lon=wp.lon,
                lat=wp.lat,
                action=wp.action,
                hold_ticks=wp.hold_ticks,
                speed_override_knots=wp.speed_override_knots,
            )
            for wp in body.waypoints
        ],
        target_speed_knots=body.target_speed_knots,
        rtb_facility_id=body.rtb_facility_id,
        mission_id=body.mission_id,
    )

    queue = OrderQueue(redis)
    await queue.submit(order)

    return OrderResponse(
        order_id=order.id,
        game_id=game_id,
        platform_id=platform_id,
        order_type=order.order_type.value,
        priority=int(order.priority),
        queued=True,
    )


@router.get("/{game_id}/{platform_id}/orders")
async def peek_orders(
    game_id: str,
    platform_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Inspect pending orders for a platform (non-destructive read)."""
    result = await db.execute(
        select(PlatformORM).where(
            PlatformORM.session_id == uuid.UUID(game_id),
            PlatformORM.id == uuid.UUID(platform_id),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Platform not found")

    redis = get_redis()
    queue = OrderQueue(redis)
    all_orders = await queue.peek(game_id, count=200)
    platform_orders = [o for o in all_orders if o.platform_id == platform_id]
    return [
        {
            "order_id": o.id,
            "order_type": o.order_type.value,
            "priority": int(o.priority),
            "submission_tick": o.submission_tick,
            "waypoints": [w.model_dump() for w in o.waypoints],
            "target_speed_knots": o.target_speed_knots,
        }
        for o in platform_orders
    ]


@router.delete("/{game_id}/{platform_id}/orders", status_code=204)
async def cancel_orders(
    game_id: str,
    platform_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> None:
    """Cancel all pending orders for a platform."""
    result = await db.execute(
        select(PlatformORM).where(
            PlatformORM.session_id == uuid.UUID(game_id),
            PlatformORM.id == uuid.UUID(platform_id),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Platform not found")

    redis = get_redis()
    queue = OrderQueue(redis)
    await queue.cancel_platform_orders(game_id, platform_id)


def _platform_to_dict(p: PlatformORM) -> dict:
    return {
        "id": str(p.id),
        "designation": p.designation,
        "platform_class": p.platform_class,
        "type_key": p.type_key,
        "faction": p.faction,
        "status": p.status,
        "position": [p.position_lon, p.position_lat] if p.position_lon is not None else None,
        "heading": p.heading,
        "speed": p.speed,
        "altitude": p.altitude,
        "fuel_state": p.fuel_state,
        "health": p.health,
        "weapons_remaining": (p.ammo_state or {}).get("magazine", 1.0) if isinstance(p.ammo_state, dict) else 1.0,
        "maintenance_due_tick": p.maintenance_due_tick,
        "assigned_mission_id": str(p.assigned_mission_id) if p.assigned_mission_id else None,
        "assigned_tf_id": str(p.assigned_tf_id) if p.assigned_tf_id else None,
        "ammo_state": p.ammo_state,
        "created_tick": p.created_tick,
        "destroyed_tick": p.destroyed_tick,
    }
