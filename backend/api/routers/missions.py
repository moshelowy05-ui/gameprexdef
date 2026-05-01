import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_auth, get_session
from shared.db_models import MissionORM
from shared.enums import MissionType, MissionStatus

router = APIRouter()


class CreateMissionRequest(BaseModel):
    game_id: str
    name: str
    mission_type: str
    assigned_tf_id: str
    target: dict
    roe: dict | None = None
    waypoints: list[dict] | None = None
    priority: int = 5
    commander_notes: str = ""


@router.post("/", response_model=dict)
async def create_mission(
    req: CreateMissionRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    mission = MissionORM(
        session_id=uuid.UUID(req.game_id),
        name=req.name,
        mission_type=req.mission_type,
        status=MissionStatus.PLANNED,
        assigned_tf_id=uuid.UUID(req.assigned_tf_id),
        target=req.target,
        roe=req.roe or {},
        waypoints=req.waypoints or [],
        priority=req.priority,
        commander_notes=req.commander_notes,
        events=[],
    )
    db.add(mission)
    await db.flush()
    return _mission_to_dict(mission)


@router.get("/{game_id}", response_model=list[dict])
async def list_missions(
    game_id: str,
    status: str | None = None,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = select(MissionORM).where(MissionORM.session_id == uuid.UUID(game_id))
    if status:
        stmt = stmt.where(MissionORM.status == status)
    result = await db.execute(stmt.order_by(MissionORM.priority.desc()))
    return [_mission_to_dict(m) for m in result.scalars().all()]


@router.get("/{game_id}/{mission_id}")
async def get_mission(
    game_id: str,
    mission_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(MissionORM).where(
            MissionORM.session_id == uuid.UUID(game_id),
            MissionORM.id == uuid.UUID(mission_id),
        )
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _mission_to_dict(m)


@router.patch("/{game_id}/{mission_id}/status")
async def update_mission_status(
    game_id: str,
    mission_id: str,
    status: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(MissionORM).where(
            MissionORM.session_id == uuid.UUID(game_id),
            MissionORM.id == uuid.UUID(mission_id),
        )
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Mission not found")
    if status not in MissionStatus.__members__:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    m.status = status
    return _mission_to_dict(m)


def _mission_to_dict(m: MissionORM) -> dict:
    return {
        "id": str(m.id),
        "name": m.name,
        "mission_type": m.mission_type,
        "status": m.status,
        "assigned_tf_id": str(m.assigned_tf_id),
        "target": m.target,
        "roe": m.roe,
        "start_tick": m.start_tick,
        "end_tick": m.end_tick,
        "waypoints": m.waypoints,
        "priority": m.priority,
        "commander_notes": m.commander_notes,
        "events": m.events,
    }
