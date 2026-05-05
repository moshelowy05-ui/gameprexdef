"""
Simulation engine data models.

Separate from shared/models.py (Pydantic domain models) — these are the
internal representations optimised for tick-loop performance. We use
dataclasses for hot-path objects to avoid Pydantic validation overhead.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


# ── Order priority (lower int = processed first) ─────────────────────────────

class OrderPriority(IntEnum):
    NCA_OVERRIDE = 0    # Nuclear / highest authority override
    EMERGENCY    = 100  # Evasion, emergency RTB
    MISSION      = 200  # Mission-assigned waypoints
    LOGISTICS    = 300  # Fuel/maintenance-driven RTB
    ROUTINE      = 400  # Normal operations


class OrderType(StrEnum):
    MOVE_TO   = "MOVE_TO"   # Follow waypoint list
    HOLD      = "HOLD"      # Stop at current position
    RTB       = "RTB"       # Return to assigned base
    SET_SPEED = "SET_SPEED" # Change cruise speed
    PATROL    = "PATROL"    # Repeat waypoint loop
    ABORT     = "ABORT"     # Cancel all pending orders


# ── Order (Pydantic for serialisation / API surface) ─────────────────────────

class OrderWaypoint(BaseModel):
    lon: float
    lat: float
    action: str = "TRANSIT"           # TRANSIT | HOLD | STRIKE | RECON | RTB
    hold_ticks: int = 0
    speed_override_knots: float | None = None


class PlatformOrder(BaseModel):
    id: str                            # UUID string
    game_id: str
    platform_id: str
    order_type: OrderType
    priority: OrderPriority = OrderPriority.ROUTINE
    submission_tick: int = 0
    waypoints: list[OrderWaypoint] = []
    target_speed_knots: float | None = None
    rtb_facility_id: str | None = None
    mission_id: str | None = None


# ── Hot-path state (dataclasses — no validation overhead per tick) ────────────

@dataclass
class PlatformHotState:
    """In-memory representation of a platform during a tick.  Fields are a
    projection of PlatformORM, plus cached PlatformType attributes needed
    by subsystems (burn_rate, max_range) so we avoid repeated DB joins."""
    id: str
    game_id: str
    type_key: str
    faction: str
    status: str
    pos_lon: float
    pos_lat: float
    heading: float            # degrees true (0 = North)
    speed_knots: float
    fuel_state: float         # 0.0 – 1.0
    health: float             # 0.0 – 1.0
    # From PlatformType — cached at load time
    fuel_burn_rate_per_tick: float
    fuel_capacity_lbs: float
    cruise_speed_knots: float
    max_range_nm: float
    is_nuclear: bool          # nuclear-powered → no fuel burn
    # Dirty flag — only write back to DB/cache if True
    is_dirty: bool = False


@dataclass
class MovementState:
    """Per-platform movement intent, stored in Redis between ticks."""
    waypoints: list[list[float]]       # [[lon, lat, speed_override_or_0], ...]
    current_wp_index: int = 0
    hold_ticks_remaining: int = 0
    patrol_loop: bool = False          # if True, cycle back to wp[0] on completion
    rtb_position: list[float] | None = None  # [lon, lat] of assigned base


@dataclass
class CombatEngagement:
    """Records one engagement attempt — attacker fires at target."""
    tick: int
    attacker_id: str
    target_id: str
    attacker_faction: str
    weapon_type: str
    distance_nm: float
    hit: bool
    damage: float
    narrative: str


@dataclass
class TickResult:
    """Returned by TickEngine.run_tick — summarises what happened."""
    game_id: str
    tick: int
    wall_ms: float                     # real-time duration of this tick
    platforms_processed: int
    platforms_moved: int
    platforms_rtb_triggered: int
    deltas: list[PlatformDelta]
    events: list[SimEvent]
    platforms_refueling: int = 0
    warnings: list[str] = field(default_factory=list)
    combat_engagements: list[dict] = field(default_factory=list)
    intel_updates: list[dict] = field(default_factory=list)
    game_over: dict | None = None
    mission_updates: list[dict] = field(default_factory=list)
    production_deliveries: list[dict] = field(default_factory=list)
    scenario_events: list[dict] = field(default_factory=list)


# ── Output types (Pydantic for serialisation) ─────────────────────────────────

class PlatformDelta(BaseModel):
    """Minimal update broadcast to WebSocket clients.  Only changed fields set."""
    id: str
    position: list[float] | None = None   # [lon, lat]
    heading: float | None = None
    speed: float | None = None
    fuel_state: float | None = None
    health: float | None = None
    status: str | None = None


class SimEventType(StrEnum):
    PLATFORM_MOVED        = "PLATFORM_MOVED"
    WAYPOINT_REACHED      = "WAYPOINT_REACHED"
    MISSION_COMPLETE      = "MISSION_COMPLETE"
    FUEL_LOW              = "FUEL_LOW"
    FUEL_BINGO            = "FUEL_BINGO"
    RTB_TRIGGERED         = "RTB_TRIGGERED"
    FUEL_EXHAUSTED        = "FUEL_EXHAUSTED"
    PLATFORM_STATUS_CHANGE = "PLATFORM_STATUS_CHANGE"
    TICK_COMPLETE         = "TICK_COMPLETE"


class SimEvent(BaseModel):
    type: SimEventType
    tick: int
    platform_id: str | None = None
    game_id: str = ""
    data: dict[str, Any] = {}
    narrative: str = ""
    timestamp: float = field(default_factory=time.time)

    # Pydantic v2 — field with default_factory must be declared properly
    model_config = {"arbitrary_types_allowed": True}


# ── Redis key helpers ─────────────────────────────────────────────────────────

class RKeys:
    """Centralised Redis key builder — prevents key-string scatter."""

    @staticmethod
    def active_games() -> str:
        return "sim:active_games"

    @staticmethod
    def game_platform_ids(game_id: str) -> str:
        return f"sim:game:{game_id}:platform_ids"

    @staticmethod
    def platform_hot(platform_id: str) -> str:
        return f"sim:plat:{platform_id}:hot"

    @staticmethod
    def platform_movement(platform_id: str) -> str:
        return f"sim:plat:{platform_id}:movement"

    @staticmethod
    def platform_type_cache(type_key: str) -> str:
        return f"sim:ptype:{type_key}"

    @staticmethod
    def order_queue(game_id: str) -> str:
        return f"sim:orders:{game_id}"

    @staticmethod
    def game_tick(game_id: str) -> str:
        return f"sim:game:{game_id}:tick"

    @staticmethod
    def event_stream(game_id: str) -> str:
        return f"sim:events:{game_id}"
