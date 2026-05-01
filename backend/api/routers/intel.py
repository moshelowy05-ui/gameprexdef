import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_auth, get_session
from shared.db_models import IntelTrackORM

router = APIRouter()


@router.get("/{game_id}/tracks", response_model=list[dict])
async def list_tracks(
    game_id: str,
    faction: str | None = None,
    track_type: str | None = None,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = select(IntelTrackORM).where(IntelTrackORM.session_id == uuid.UUID(game_id))
    if faction:
        stmt = stmt.where(IntelTrackORM.faction_observer == faction)
    if track_type:
        stmt = stmt.where(IntelTrackORM.track_type == track_type)
    result = await db.execute(stmt)
    return [_track_to_dict(t) for t in result.scalars().all()]


def _track_to_dict(t: IntelTrackORM) -> dict:
    return {
        "id": str(t.id),
        "faction_observer": t.faction_observer,
        "target_platform_id": str(t.target_platform_id) if t.target_platform_id else None,
        "track_type": t.track_type,
        "last_position": [t.last_position_lon, t.last_position_lat],
        "last_updated_tick": t.last_updated_tick,
        "estimated_heading": t.estimated_heading,
        "estimated_speed": t.estimated_speed,
        "platform_type_estimate": t.platform_type_estimate,
        "confidence": t.confidence,
        "source": t.source,
    }
