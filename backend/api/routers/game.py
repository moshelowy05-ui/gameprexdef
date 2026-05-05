"""
Game session management — create, list, load, pause/resume/speed.
Wires into AsyncTickRunner for live simulation control.
"""
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_auth, get_session
from shared.db_models import GameSessionORM, PlatformORM, FacilityORM, ResourceStateORM
from shared.enums import Faction

router = APIRouter()

SCENARIOS_DIR = Path(__file__).parent.parent.parent.parent / "scenarios"


class CreateGameRequest(BaseModel):
    scenario_id: str


class GameSummary(BaseModel):
    id: str
    scenario_id: str
    current_tick: int
    paused: bool
    tick_speed_multiplier: float


def _load_scenario(scenario_id: str) -> dict:
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    with open(path) as f:
        return json.load(f)


def _platform_type_key_for_faction(type_key: str, faction: str) -> str:
    """Adversary platforms reuse US type keys for now (same stats, different faction)."""
    return type_key


@router.post("/create", response_model=GameSummary)
async def create_game(
    req: CreateGameRequest,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> GameSummary:
    scenario = _load_scenario(req.scenario_id)
    game_id = uuid.uuid4()

    session_orm = GameSessionORM(
        id=game_id,
        scenario_id=req.scenario_id,
        current_tick=0,
        paused=True,
        tick_speed_multiplier=1.0,
        state_snapshot={
            "scenario_id": req.scenario_id,
            "objectives": scenario.get("objectives", []),
            "victory_conditions": scenario.get("victory_conditions", {}),
        },
    )
    db.add(session_orm)
    await db.flush()

    # ── Populate normalized platform rows from scenario OOB ────────────────
    initial_forces: dict = scenario.get("initial_forces", {})

    for faction_key, force_groups in initial_forces.items():
        faction = faction_key  # "US", "ADVERSARY_A", etc.
        for category in ("naval", "air", "ground"):
            for unit in force_groups.get(category, []):
                pos = unit.get("position")
                platform_faction = unit.get("faction", faction)
                db.add(PlatformORM(
                    id=uuid.uuid4(),
                    session_id=game_id,
                    designation=unit["designation"],
                    platform_class=_class_for_type_key(unit["type_key"]),
                    type_key=unit["type_key"],
                    faction=platform_faction,
                    status=unit.get("status", "ACTIVE"),
                    position_lon=pos[0] if pos else None,
                    position_lat=pos[1] if pos else None,
                    heading=0.0,
                    speed=0.0,
                    fuel_state=1.0,
                    health=1.0,
                    maintenance_due_tick=720,
                    created_tick=0,
                    ammo_state={},
                    sensor_suite={},
                ))

    # ── Populate facility rows ──────────────────────────────────────────────
    initial_facilities: dict = scenario.get("initial_facilities", {})
    for faction_key, fac_list in initial_facilities.items():
        for fac in fac_list:
            pos = fac["position"]
            db.add(FacilityORM(
                id=uuid.uuid4(),
                session_id=game_id,
                facility_type=fac["type"],
                name=fac["name"],
                faction=fac.get("faction", faction_key),
                position_lon=pos[0],
                position_lat=pos[1],
                production_slots=fac.get("production_slots", 1),
                health=1.0,
                workforce=fac.get("workforce", 1000),
                power_state="OPERATIONAL",
                production_queue=[],
                storage={},
            ))

    # ── Resource state ──────────────────────────────────────────────────────
    us_faction_cfg = scenario.get("factions", {}).get("US", {})
    db.add(ResourceStateORM(
        session_id=game_id,
        faction=Faction.US,
        tick=0,
        budget_billions=float(us_faction_cfg.get("budget_billions", 850.0)),
        budget_burn_rate_per_tick=0.097,
        fuel_reserves_barrels=700_000_000.0,
        supply_chain_disruption=0.0,
        resources_json={},
    ))

    return GameSummary(
        id=str(game_id),
        scenario_id=req.scenario_id,
        current_tick=0,
        paused=True,
        tick_speed_multiplier=1.0,
    )


def _class_for_type_key(type_key: str) -> str:
    """Infer PlatformClass from type_key naming conventions."""
    tk = type_key.upper()
    if any(k in tk for k in ("CVN", "DDG", "CG", "LHA", "LCS", "T_AO")):
        return "SHIP"
    if any(k in tk for k in ("SSN", "SSBN")):
        return "SUBMARINE"
    if any(k in tk for k in ("MQ", "RQ")):
        return "UAV"
    if any(k in tk for k in ("F35", "F22", "B21", "B2_", "B52", "E2D", "EA18", "P8", "KC", "C17", "AH64")):
        return "AIRCRAFT"
    if any(k in tk for k in ("THAAD", "PAC3", "HIMARS", "M1A2")):
        return "VEHICLE"
    if "SAT" in tk or "SATELLITE" in tk:
        return "SATELLITE"
    if "AEGIS_ASHORE" in tk:
        return "FACILITY"
    return "VEHICLE"


@router.get("/list", response_model=list[GameSummary])
async def list_games(
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[GameSummary]:
    result = await db.execute(select(GameSessionORM).order_by(GameSessionORM.created_at.desc()))
    return [_to_summary(s) for s in result.scalars().all()]


@router.get("/{game_id}", response_model=GameSummary)
async def get_game(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> GameSummary:
    s = await _get_or_404(game_id, db)
    return _to_summary(s)


@router.get("/{game_id}/state")
async def get_game_state(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    s = await _get_or_404(game_id, db)
    return s.state_snapshot


@router.get("/{game_id}/brief")
async def get_scenario_brief(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    """Return scenario objectives and victory conditions for the pre-game brief."""
    s = await _get_or_404(game_id, db)
    try:
        scenario = _load_scenario(s.scenario_id)
    except HTTPException:
        return {"objectives": [], "victory_conditions": {}, "factions": {}}
    return {
        "scenario_id": s.scenario_id,
        "name": scenario.get("name", s.scenario_id),
        "description": scenario.get("description", ""),
        "classification": scenario.get("classification", "UNCLASSIFIED"),
        "theater": scenario.get("theater", {}),
        "objectives": scenario.get("objectives", []),
        "victory_conditions": scenario.get("victory_conditions", {}),
        "factions": scenario.get("factions", {}),
        "duration_ticks": scenario.get("duration_ticks", 720),
    }


@router.post("/{game_id}/pause")
async def pause_game(
    request: Request,
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    s = await _get_or_404(game_id, db)
    s.paused = True
    runner = getattr(request.app.state, "tick_runner", None)
    if runner:
        await runner.pause_game(game_id)
    return {"paused": True, "tick": s.current_tick}


@router.post("/{game_id}/resume")
async def resume_game(
    request: Request,
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    s = await _get_or_404(game_id, db)
    s.paused = False
    runner = getattr(request.app.state, "tick_runner", None)
    if runner:
        await runner.resume_game(game_id, s.tick_speed_multiplier)
    return {"paused": False, "tick": s.current_tick}


@router.post("/{game_id}/speed")
async def set_speed(
    request: Request,
    game_id: str,
    multiplier: float,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    if multiplier < 0.25 or multiplier > 100.0:
        raise HTTPException(status_code=400, detail="Multiplier must be 0.25–100")
    s = await _get_or_404(game_id, db)
    s.tick_speed_multiplier = multiplier
    runner = getattr(request.app.state, "tick_runner", None)
    if runner and not s.paused:
        await runner.set_speed(game_id, multiplier)
    return {"tick_speed_multiplier": multiplier}


# ── helpers ──────────────────────────────────────────────────────────────────

async def _get_or_404(game_id: str, db: AsyncSession) -> GameSessionORM:
    result = await db.execute(
        select(GameSessionORM).where(GameSessionORM.id == uuid.UUID(game_id))
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Game not found")
    return s


def _to_summary(s: GameSessionORM) -> GameSummary:
    return GameSummary(
        id=str(s.id),
        scenario_id=s.scenario_id,
        current_tick=s.current_tick,
        paused=s.paused,
        tick_speed_multiplier=s.tick_speed_multiplier,
    )
