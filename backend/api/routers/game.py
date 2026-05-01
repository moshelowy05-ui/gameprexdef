import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_auth, get_session
from shared.db_models import GameSessionORM
from shared.models import GameState, ResourceState, MunitionsInventory
from shared.enums import Faction

router = APIRouter()


class CreateGameRequest(BaseModel):
    scenario_id: str


class GameSummary(BaseModel):
    id: str
    scenario_id: str
    current_tick: int
    paused: bool
    tick_speed_multiplier: float


@router.post("/create", response_model=GameSummary)
async def create_game(
    req: CreateGameRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> GameSummary:
    initial_resources = {
        Faction.US: ResourceState(
            faction=Faction.US,
            budget_billions=850.0,
            fuel_reserves_barrels=700_000_000.0,
            munitions_stockpile=MunitionsInventory(
                tomahawk=4000,
                harpoon=700,
                aim120_amraam=10000,
                aim9x_sidewinder=5000,
                sm2=3500,
                sm3=600,
                sm6=900,
                thaad_interceptor=1200,
                pac3_interceptor=3000,
                mk48_torpedo=3000,
                agm158_jassm=1500,
                agm158c_lrasm=400,
                gbu31_jdam=50000,
                gbu39_sdb=30000,
            ),
        ),
    }
    state = GameState(
        scenario_id=req.scenario_id,
        resource_states={k.value: v for k, v in initial_resources.items()},
    )

    session_orm = GameSessionORM(
        id=state.game_id,
        scenario_id=req.scenario_id,
        current_tick=0,
        paused=True,
        tick_speed_multiplier=1.0,
        state_snapshot=state.model_dump(mode="json"),
    )
    db.add(session_orm)
    await db.flush()

    return GameSummary(
        id=str(session_orm.id),
        scenario_id=session_orm.scenario_id,
        current_tick=session_orm.current_tick,
        paused=session_orm.paused,
        tick_speed_multiplier=session_orm.tick_speed_multiplier,
    )


@router.get("/list", response_model=list[GameSummary])
async def list_games(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[GameSummary]:
    result = await db.execute(select(GameSessionORM).order_by(GameSessionORM.created_at.desc()))
    sessions = result.scalars().all()
    return [
        GameSummary(
            id=str(s.id),
            scenario_id=s.scenario_id,
            current_tick=s.current_tick,
            paused=s.paused,
            tick_speed_multiplier=s.tick_speed_multiplier,
        )
        for s in sessions
    ]


@router.get("/{game_id}", response_model=GameSummary)
async def get_game(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> GameSummary:
    result = await db.execute(
        select(GameSessionORM).where(GameSessionORM.id == uuid.UUID(game_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")
    return GameSummary(
        id=str(session.id),
        scenario_id=session.scenario_id,
        current_tick=session.current_tick,
        paused=session.paused,
        tick_speed_multiplier=session.tick_speed_multiplier,
    )


@router.get("/{game_id}/state")
async def get_game_state(
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
    return session.state_snapshot


@router.post("/{game_id}/pause")
async def pause_game(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await db.execute(
        select(GameSessionORM).where(GameSessionORM.id == uuid.UUID(game_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")
    session.paused = True
    return {"paused": True}


@router.post("/{game_id}/resume")
async def resume_game(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await db.execute(
        select(GameSessionORM).where(GameSessionORM.id == uuid.UUID(game_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")
    session.paused = False
    return {"paused": False}


@router.post("/{game_id}/speed")
async def set_speed(
    game_id: str,
    multiplier: float,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    if multiplier < 0.25 or multiplier > 100.0:
        raise HTTPException(status_code=400, detail="Multiplier must be 0.25–100")
    result = await db.execute(
        select(GameSessionORM).where(GameSessionORM.id == uuid.UUID(game_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")
    session.tick_speed_multiplier = multiplier
    return {"tick_speed_multiplier": multiplier}
