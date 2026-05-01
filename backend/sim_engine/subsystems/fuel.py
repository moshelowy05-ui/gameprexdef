"""
Fuel subsystem — vectorized fuel burn, threshold alerts, RTB trigger.

Fuel model:
  - Each tick, every non-nuclear active platform burns fuel proportional to
    its PlatformType.fuel_burn_rate_per_tick (lbs/tick at cruise speed).
  - Speed modifier: burn scales with (actual_speed / cruise_speed)^1.5
    (roughly matches real turbine fuel-flow physics at different power settings).
  - Stationary platforms burn at idle rate: 15% of cruise burn rate.
  - fuel_state is a normalized float [0.0, 1.0]:
      fuel_state = remaining_lbs / fuel_capacity_lbs

Thresholds:
  LOW_FUEL_THRESHOLD  = 0.20  → FUEL_LOW alert (20% remaining)
  BINGO_FUEL          = 0.10  → FUEL_BINGO alert + auto RTB order queued
  EXHAUSTED           = 0.00  → platform DESTROYED (if airborne) or DISABLED

Auto-RTB:
  On BINGO, the fuel system inserts an RTB order at LOGISTICS priority into
  the order queue (passed in as a parameter).  The caller is responsible for
  committing that order; the fuel system does not touch Redis directly.

Time complexity: O(N) vectorized for burn calculation.
  BINGO threshold check: O(B) where B = bingo platforms (usually 0–5 per tick).
"""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import NamedTuple

import numpy as np

from sim_engine.models import (
    OrderPriority,
    PlatformDelta,
    PlatformHotState,
    PlatformOrder,
    SimEvent,
    SimEventType,
)
from sim_engine.order_queue import OrderQueue

log = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

LOW_FUEL_THRESHOLD: float = 0.20    # issue advisory alert
BINGO_FUEL_THRESHOLD: float = 0.10  # mandatory RTB
EXHAUSTED_THRESHOLD: float = 0.005  # effectively zero

# Idle burn fraction (stationary, engines running)
IDLE_BURN_FRACTION: float = 0.15

# Speed-to-burn exponent (turbine power curve approximation)
SPEED_BURN_EXPONENT: float = 1.5

# ── Default base positions for RTB (used when no facility assigned) ───────────
# In Phase 1 these are hard-coded to the Taiwan Strait scenario forward bases.
# Phase 2 will assign bases per platform via the facility system.
_DEFAULT_RTB_POSITIONS: dict[str, list[float]] = {
    "AIRCRAFT":  [127.77, 26.35],  # Kadena AB
    "SHIP":      [139.67, 35.29],  # Yokosuka Naval Base
    "SUBMARINE": [139.67, 35.29],
    "UAV":       [144.93, 13.44],  # Andersen AFB
    "VEHICLE":   [127.77, 26.35],
    "DEFAULT":   [127.77, 26.35],
}


def _rtb_position_for(platform: PlatformHotState) -> list[float]:
    return _DEFAULT_RTB_POSITIONS.get(
        platform.faction == "US" and platform.type_key or "DEFAULT",
        _DEFAULT_RTB_POSITIONS["DEFAULT"],
    )


# ── Result type ───────────────────────────────────────────────────────────────

class FuelTickResult(NamedTuple):
    platforms_burned: int
    platforms_low_fuel: int
    platforms_bingo: int
    platforms_exhausted: int
    deltas: list[PlatformDelta]
    events: list[SimEvent]
    rtb_orders: list[PlatformOrder]   # to be submitted by the caller


# ── Subsystem ────────────────────────────────────────────────────────────────

class FuelSubsystem:
    """
    Processes fuel consumption for all active platforms in one tick.

    Previously-triggered BINGO platforms are tracked to avoid re-firing
    the RTB order every tick (stored as a set on the instance — per-game
    instances prevent cross-contamination).
    """

    def __init__(self, game_id: str) -> None:
        self._game_id = game_id
        # Platforms already in RTB state — suppress re-trigger
        self._bingo_triggered: set[str] = set()
        # Platforms already alerted for LOW_FUEL — suppress duplicate alerts
        self._low_fuel_alerted: set[str] = set()

    def resolve_tick(
        self,
        platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> FuelTickResult:
        """
        Burn fuel for all active, non-nuclear platforms.

        Steps:
          1. Build arrays for all eligible platforms (O(N) list comp)
          2. Compute burn per tick (O(N) vectorized NumPy)
          3. Update fuel_state (O(N) vectorized)
          4. Check LOW_FUEL / BINGO / EXHAUSTED thresholds (O(N) mask ops)
          5. Write dirty flags and deltas (O(N))

        Returns FuelTickResult with events and RTB orders to enqueue.
        """
        # ── Phase 1: Gather eligible platforms ───────────────────────────────
        eligible_ids: list[str] = []
        eligible_platforms: list[PlatformHotState] = []

        for pid, p in platforms.items():
            if p.is_nuclear:
                continue  # nuclear-powered → no fuel consumption
            if p.status in ("DESTROYED", "RETIRED", "IN_PRODUCTION"):
                continue
            if p.fuel_capacity_lbs <= 0.0:
                continue  # no fuel tank (e.g., ground facilities)
            eligible_ids.append(pid)
            eligible_platforms.append(p)

        if not eligible_ids:
            return FuelTickResult(0, 0, 0, 0, [], [], [])

        n = len(eligible_ids)

        # ── Phase 2: Vectorized burn calculation ──────────────────────────────
        burn_rates = np.array(
            [p.fuel_burn_rate_per_tick for p in eligible_platforms], dtype=np.float64
        )
        cruise_speeds = np.array(
            [p.cruise_speed_knots for p in eligible_platforms], dtype=np.float64
        )
        actual_speeds = np.array(
            [p.speed_knots for p in eligible_platforms], dtype=np.float64
        )
        fuel_states = np.array(
            [p.fuel_state for p in eligible_platforms], dtype=np.float64
        )

        # Speed modifier: idle (0 speed) burns at IDLE_BURN_FRACTION
        # Moving platforms burn proportional to (speed/cruise)^SPEED_BURN_EXPONENT
        speed_ratio = np.where(
            cruise_speeds > 0,
            np.clip(actual_speeds / cruise_speeds, 0.0, 3.0),
            0.0,
        )
        burn_modifier = np.where(
            actual_speeds < 0.1,
            IDLE_BURN_FRACTION,
            speed_ratio ** SPEED_BURN_EXPONENT,
        )

        # Actual burn in lbs this tick
        burn_lbs = burn_rates * burn_modifier

        # Convert to fuel_state reduction:  Δstate = burn_lbs / capacity_lbs
        capacities = np.array(
            [p.fuel_capacity_lbs for p in eligible_platforms], dtype=np.float64
        )
        delta_state = np.where(capacities > 0, burn_lbs / capacities, 0.0)

        new_fuel_states = np.clip(fuel_states - delta_state, 0.0, 1.0)

        # ── Phase 3: Threshold detection ─────────────────────────────────────
        was_low  = fuel_states < LOW_FUEL_THRESHOLD
        now_low  = new_fuel_states < LOW_FUEL_THRESHOLD
        new_low_mask = now_low & ~was_low        # just crossed LOW threshold

        was_bingo = fuel_states < BINGO_FUEL_THRESHOLD
        now_bingo = new_fuel_states < BINGO_FUEL_THRESHOLD
        new_bingo_mask = now_bingo & ~was_bingo  # just crossed BINGO threshold

        now_exhausted = new_fuel_states <= EXHAUSTED_THRESHOLD

        # ── Phase 4: Write results ────────────────────────────────────────────
        deltas: list[PlatformDelta] = []
        events: list[SimEvent] = []
        rtb_orders: list[PlatformOrder] = []

        low_count = 0
        bingo_count = 0
        exhausted_count = 0

        for i, pid in enumerate(eligible_ids):
            platform = eligible_platforms[i]
            new_fs = float(new_fuel_states[i])

            if abs(new_fs - platform.fuel_state) < 1e-8:
                continue  # no change (shouldn't happen but guard anyway)

            platform.fuel_state = new_fs
            platform.is_dirty = True

            deltas.append(PlatformDelta(id=pid, fuel_state=round(new_fs, 4)))

            # LOW_FUEL alert (suppress repeat)
            if new_low_mask[i] and pid not in self._low_fuel_alerted:
                self._low_fuel_alerted.add(pid)
                low_count += 1
                events.append(SimEvent(
                    type=SimEventType.FUEL_LOW,
                    tick=tick,
                    platform_id=pid,
                    game_id=self._game_id,
                    data={"fuel_state": new_fs},
                    narrative=(
                        f"FUEL LOW: {platform.type_key} at "
                        f"{round(new_fs * 100)}% fuel"
                    ),
                ))

            # BINGO — trigger RTB (suppress repeat)
            if new_bingo_mask[i] and pid not in self._bingo_triggered:
                self._bingo_triggered.add(pid)
                bingo_count += 1
                rtb_pos = _rtb_position_for(platform)
                rtb_order = OrderQueue.make_rtb_order(
                    game_id=self._game_id,
                    platform_id=pid,
                    rtb_position=rtb_pos,
                    priority=OrderPriority.LOGISTICS,
                    tick=tick,
                )
                rtb_orders.append(rtb_order)
                events.append(SimEvent(
                    type=SimEventType.FUEL_BINGO,
                    tick=tick,
                    platform_id=pid,
                    game_id=self._game_id,
                    data={"fuel_state": new_fs, "rtb_position": rtb_pos},
                    narrative=(
                        f"BINGO FUEL: {platform.type_key} auto-RTB ordered "
                        f"({round(new_fs * 100)}% remaining)"
                    ),
                ))

            # EXHAUSTED
            if now_exhausted[i]:
                exhausted_count += 1
                # Airborne platforms crash; surface platforms go dead in water
                is_airborne = platform.status in ("AIRBORNE", "IN_TRANSIT") and \
                              platform.type_key not in ("SHIP", "SUBMARINE", "VEHICLE")
                new_status = "DESTROYED" if is_airborne else "ACTIVE"
                platform.status = new_status
                platform.speed_knots = 0.0
                platform.is_dirty = True
                events.append(SimEvent(
                    type=SimEventType.FUEL_EXHAUSTED,
                    tick=tick,
                    platform_id=pid,
                    game_id=self._game_id,
                    data={"destroyed": is_airborne, "status": new_status},
                    narrative=(
                        f"FUEL EXHAUSTED: {platform.type_key} "
                        + ("DESTROYED (fuel exhaustion)" if is_airborne else "dead in water")
                    ),
                ))

        return FuelTickResult(
            platforms_burned=n,
            platforms_low_fuel=low_count,
            platforms_bingo=bingo_count,
            platforms_exhausted=exhausted_count,
            deltas=deltas,
            events=events,
            rtb_orders=rtb_orders,
        )

    def reset_bingo_flags(self, platform_ids: list[str]) -> None:
        """Clear BINGO flags when platforms are refuelled."""
        for pid in platform_ids:
            self._bingo_triggered.discard(pid)
            self._low_fuel_alerted.discard(pid)
