import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_auth, get_session
from shared.db_models import TaskForceORM

router = APIRouter()


class CreateTaskForceRequest(BaseModel):
    game_id: str
    name: str
    commander_unit_id: str
    assigned_unit_ids: list[str] = []
    formation: dict | None = None


class AddUnitsRequest(BaseModel):
    unit_ids: list[str]


@router.post("/", response_model=dict)
async def create_task_force(
    req: CreateTaskForceRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    tf = TaskForceORM(
        session_id=uuid.UUID(req.game_id),
        name=req.name,
        commander_unit_id=uuid.UUID(req.commander_unit_id),
        assigned_unit_ids=[str(uid) for uid in req.assigned_unit_ids],
        formation=req.formation or {"type": "STANDARD", "spacing_nm": 2.0},
        status="ASSEMBLING",
    )
    db.add(tf)
    await db.flush()
    return _tf_to_dict(tf)


@router.get("/{game_id}", response_model=list[dict])
async def list_task_forces(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    result = await db.execute(
        select(TaskForceORM).where(TaskForceORM.session_id == uuid.UUID(game_id))
    )
    return [_tf_to_dict(tf) for tf in result.scalars().all()]


@router.get("/{game_id}/{tf_id}")
async def get_task_force(
    game_id: str,
    tf_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(TaskForceORM).where(
            TaskForceORM.session_id == uuid.UUID(game_id),
            TaskForceORM.id == uuid.UUID(tf_id),
        )
    )
    tf = result.scalar_one_or_none()
    if not tf:
        raise HTTPException(status_code=404, detail="Task force not found")
    return _tf_to_dict(tf)


@router.post("/{game_id}/{tf_id}/units")
async def add_units(
    game_id: str,
    tf_id: str,
    req: AddUnitsRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(TaskForceORM).where(
            TaskForceORM.session_id == uuid.UUID(game_id),
            TaskForceORM.id == uuid.UUID(tf_id),
        )
    )
    tf = result.scalar_one_or_none()
    if not tf:
        raise HTTPException(status_code=404, detail="Task force not found")
    existing = set(tf.assigned_unit_ids)
    for uid in req.unit_ids:
        existing.add(uid)
    tf.assigned_unit_ids = list(existing)
    return _tf_to_dict(tf)


@router.delete("/{game_id}/{tf_id}/units/{unit_id}")
async def remove_unit(
    game_id: str,
    tf_id: str,
    unit_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(TaskForceORM).where(
            TaskForceORM.session_id == uuid.UUID(game_id),
            TaskForceORM.id == uuid.UUID(tf_id),
        )
    )
    tf = result.scalar_one_or_none()
    if not tf:
        raise HTTPException(status_code=404, detail="Task force not found")
    tf.assigned_unit_ids = [uid for uid in tf.assigned_unit_ids if uid != unit_id]
    return _tf_to_dict(tf)


def _tf_to_dict(tf: TaskForceORM) -> dict:
    return {
        "id": str(tf.id),
        "name": tf.name,
        "commander_unit_id": str(tf.commander_unit_id),
        "assigned_unit_ids": tf.assigned_unit_ids,
        "platform_count": len(tf.assigned_unit_ids),
        "mission_id": str(tf.mission_id) if tf.mission_id else None,
        "formation": tf.formation,
        "status": tf.status,
        "logistics_node_id": str(tf.logistics_node_id) if tf.logistics_node_id else None,
    }
