"""
Defense Industrial Base router — resource states, production summaries.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_auth, get_session
from shared.db_models import GameSessionORM, ResourceStateORM

router = APIRouter()


@router.get("/{game_id}/resources")
async def get_resources(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    result = await db.execute(
        select(GameSessionORM).where(GameSessionORM.id == uuid.UUID(game_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")
    snapshot = session.state_snapshot
    return snapshot.get("resource_states", {})


@router.get("/{game_id}/production-summary")
async def get_production_summary(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    """Aggregate view of all active production orders across all facilities."""
    result = await db.execute(
        select(GameSessionORM).where(GameSessionORM.id == uuid.UUID(game_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    from shared.db_models import FacilityORM
    fac_result = await db.execute(
        select(FacilityORM).where(FacilityORM.session_id == uuid.UUID(game_id))
    )
    facilities = fac_result.scalars().all()

    all_orders = []
    for f in facilities:
        for order in f.production_queue:
            all_orders.append({
                "facility_id": str(f.id),
                "facility_name": f.name,
                "facility_type": f.facility_type,
                **order,
            })

    return {
        "total_orders": len(all_orders),
        "orders": all_orders,
    }
