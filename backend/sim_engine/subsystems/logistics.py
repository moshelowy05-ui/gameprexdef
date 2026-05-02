"""
LogisticsSubsystem — refueling and resupply at base.

Refuel model:
  A stopped US platform (speed < 1 knot, status ACTIVE/DOCKED) with fuel < 1.0
  receives REFUEL_RATE_PER_TICK per tick until full.

  This represents the platform having arrived at its RTB base and being
  serviced. PLAN/adversary platforms are not tracked here (handled by their
  own supply system).

Resupply:
  Phase 4 stub — ammo resupply tracked but not implemented.

FuelSubsystem BINGO flags are cleared when a platform fully refuels.
"""
from __future__ import annotations

import logging
from typing import NamedTuple

from sim_engine.models import (
    PlatformDelta,
    PlatformHotState,
    SimEvent,
    SimEventType,
)
from sim_engine.subsystems.fuel import FuelSubsystem

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

REFUEL_RATE_PER_TICK = 0.12   # 100% fuel in ~9 ticks (9 game hours) at base
MIN_SPEED_FOR_REFUEL = 1.0    # knots — must be effectively stopped


# ── Result type ───────────────────────────────────────────────────────────────

class LogisticsTickResult(NamedTuple):
    platforms_refueling: int    # count currently receiving fuel
    platforms_refueled: int     # count that reached 100% this tick
    deltas: list[PlatformDelta]
    events: list[SimEvent]      # PLATFORM_STATUS_CHANGE when refuel complete


# ── Subsystem ─────────────────────────────────────────────────────────────────

class LogisticsSubsystem:
    def __init__(self, game_id: str, fuel_subsystem: FuelSubsystem) -> None:
        self._game_id = game_id
        self._fuel = fuel_subsystem  # reference so we can call reset_bingo_flags

    def resolve_tick(
        self,
        platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> LogisticsTickResult:
        """
        Refuel all stopped, eligible platforms.

        Eligible: US faction, not DESTROYED/RETIRED/IN_PRODUCTION,
                  speed_knots < MIN_SPEED_FOR_REFUEL,
                  fuel_state < 1.0,
                  fuel_capacity_lbs > 0 (has a fuel system)
        """
        deltas: list[PlatformDelta] = []
        events: list[SimEvent] = []
        platforms_refueling = 0
        platforms_refueled = 0
        newly_full: list[str] = []

        for pid, platform in platforms.items():
            # Eligibility checks
            if platform.faction != "US":
                continue
            if platform.status in ("DESTROYED", "RETIRED", "IN_PRODUCTION"):
                continue
            if platform.speed_knots >= MIN_SPEED_FOR_REFUEL:
                continue
            if platform.fuel_state >= 1.0:
                continue
            if platform.fuel_capacity_lbs <= 0:
                continue

            platforms_refueling += 1

            new_fs = min(1.0, platform.fuel_state + REFUEL_RATE_PER_TICK)
            new_fs = round(new_fs, 4)

            platform.fuel_state = new_fs
            platform.is_dirty = True

            deltas.append(PlatformDelta(id=pid, fuel_state=new_fs))

            if new_fs >= 1.0:
                platforms_refueled += 1
                newly_full.append(pid)
                events.append(SimEvent(
                    type=SimEventType.PLATFORM_STATUS_CHANGE,
                    tick=tick,
                    platform_id=pid,
                    game_id=self._game_id,
                    data={"fuel_state": new_fs},
                    narrative=(
                        f"REFUELED: {platform.type_key} fully refueled at base "
                        f"— ready for tasking"
                    ),
                ))

        if newly_full:
            self._fuel.reset_bingo_flags(newly_full)

        return LogisticsTickResult(
            platforms_refueling=platforms_refueling,
            platforms_refueled=platforms_refueled,
            deltas=deltas,
            events=events,
        )
