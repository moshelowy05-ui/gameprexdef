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
    # Submarines
    if any(k in tk for k in ("CVN", "SSN", "SSBN", "TYPE093", "TYPE094", "TYPE039")):
        if tk.startswith("CVN"):
            return "SHIP"
        return "SUBMARINE"
    # Surface ships
    if any(k in tk for k in ("DDG", "CG", "LHA", "LCS", "T_AO", "FFG",
                               "TYPE055", "TYPE052", "TYPE054", "TYPE071", "TYPE075", "TYPE056")):
        return "SHIP"
    # Aircraft
    if any(k in tk for k in ("F35", "F22", "B21", "B2_", "B52", "E2D", "EA18", "P8", "KC", "C17",
                               "AH64", "J20", "J16", "J11", "J10", "H6", "KJ")):
        return "AIRCRAFT"
    # UAVs
    if any(k in tk for k in ("MQ", "RQ", "WZ", "TB_", "WING")):
        return "UAV"
    # Vehicles
    if any(k in tk for k in ("THAAD", "PAC3", "HIMARS", "M1A2", "DF21", "DF26", "HHQ9", "YJ18",
                               "DF_", "HHQ_", "YJ_")):
        return "VEHICLE"
    # Facilities
    if any(k in tk for k in ("AEGIS_ASHORE", "_BATTERY", "_DEPOT", "_PLANT", "_FACTORY")):
        return "FACILITY"
    if any(k in tk for k in ("SAT", "SATELLITE")):
        return "SATELLITE"
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


@router.get("/{game_id}/objectives")
async def get_objectives(
    game_id: str,
    _user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> Any:
    """Return scenario objectives with live completion-status computed from platform state."""
    s = await _get_or_404(game_id, db)
    try:
        scenario = _load_scenario(s.scenario_id)
    except HTTPException:
        return {"objectives": []}

    raw_objectives = scenario.get("objectives", [])
    gid = uuid.UUID(game_id)

    # ── Aggregate platform counts from DB ─────────────────────────────────────
    result = await db.execute(
        select(PlatformORM.faction, PlatformORM.platform_class, PlatformORM.status, PlatformORM.type_key)
        .where(PlatformORM.session_id == gid)
    )
    rows = result.all()

    us_ships          = [r for r in rows if r.faction == "US" and r.platform_class == "SHIP"]
    us_subs           = [r for r in rows if r.faction == "US" and r.platform_class == "SUBMARINE"]
    adv_ships         = [r for r in rows if r.faction in ("ADVERSARY_A", "PLAN") and r.platform_class == "SHIP"]
    adv_facilities    = [r for r in rows if r.faction in ("ADVERSARY_A", "PLAN") and r.platform_class in ("FACILITY", "VEHICLE")]
    us_carriers       = [r for r in rows if r.type_key.startswith("CVN_") and r.faction == "US"]

    us_ships_alive    = len([r for r in us_ships if r.status != "DESTROYED"])
    us_subs_alive     = len([r for r in us_subs if r.status != "DESTROYED"])
    adv_ships_total   = len(adv_ships)
    adv_ships_dest    = len([r for r in adv_ships if r.status == "DESTROYED"])
    adv_fac_total     = len(adv_facilities)
    adv_fac_dest      = len([r for r in adv_facilities if r.status == "DESTROYED"])
    carriers_total    = len(us_carriers)
    carriers_alive    = len([r for r in us_carriers if r.status != "DESTROYED"])

    def _obj_status(obj_id: str) -> tuple[str, float, str]:
        """Return (status, progress 0-1, detail_string)."""
        # OBJ_01 — Maritime Superiority: enough US naval units active
        if obj_id == "OBJ_01":
            needed = 4
            current = us_ships_alive + us_subs_alive
            prog = min(1.0, current / max(needed, 1))
            if carriers_total and carriers_alive == 0:
                return "FAILED", 0.0, "All US carriers destroyed"
            if current >= needed:
                return "COMPLETE", 1.0, f"{current} US naval units active"
            return "ACTIVE", prog, f"{current}/{needed}+ US naval units active"

        # OBJ_02 — Suppress Air Defense: adversary SAM/facility attrition
        if obj_id == "OBJ_02":
            if adv_fac_total == 0:
                return "PENDING", 0.0, "No adversary installations detected"
            prog = adv_fac_dest / adv_fac_total
            if prog >= 0.5:
                return "COMPLETE", prog, f"{adv_fac_dest}/{adv_fac_total} installations neutralized"
            return "ACTIVE", prog, f"{adv_fac_dest}/{adv_fac_total} installations neutralized"

        # OBJ_03 — Break the Blockade: adversary surface ships destroyed
        if obj_id == "OBJ_03":
            if adv_ships_total == 0:
                return "PENDING", 0.0, "No adversary surface forces detected"
            prog = adv_ships_dest / adv_ships_total
            if prog >= 0.6:
                return "COMPLETE", prog, f"{adv_ships_dest}/{adv_ships_total} PLAN vessels destroyed"
            return "ACTIVE", prog, f"{adv_ships_dest}/{adv_ships_total} PLAN vessels destroyed"

        # OBJ_04 — Protect Taiwan's Air Infrastructure (defensive)
        if obj_id == "OBJ_04":
            if carriers_total == 0:
                return "PENDING", 1.0, "No US carriers tracked"
            if carriers_alive == 0:
                return "FAILED", 0.0, "All US carriers destroyed — sea control lost"
            prog = carriers_alive / carriers_total
            return "ACTIVE" if prog < 1.0 else "COMPLETE", prog, \
                f"{carriers_alive}/{carriers_total} US carriers intact"

        # Generic fallback — no computed status
        return "PENDING", 0.0, ""

    enriched = []
    for obj in raw_objectives:
        status, progress, detail = _obj_status(obj.get("id", ""))
        enriched.append({
            **obj,
            "status": status,
            "progress": round(progress, 3),
            "detail": detail,
        })

    return {
        "scenario_id": s.scenario_id,
        "current_tick": s.current_tick,
        "objectives": enriched,
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
