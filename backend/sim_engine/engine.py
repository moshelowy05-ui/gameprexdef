"""
TickEngine — deterministic, single-tick simulation executor.

One TickEngine instance per game session.  The AsyncTickRunner creates and
owns these instances; they are not shared across games.

═══════════════════════════════════════════════════════════════════════════════
TICK LIFECYCLE  (enforced order, documented as the canonical spec)
═══════════════════════════════════════════════════════════════════════════════

 1. LOAD
    ├── StateManager.load_game_platforms()   → PlatformHotState dict (Redis → DB fallback)
    ├── StateManager.load_movement_states()  → MovementState dict (Redis)
    └── OrderQueue.pop_all()                 → PlatformOrder list (Redis ZPOPMIN, atomic)

 2. ORDER RESOLUTION  (deterministic — sorted by priority ASC, tick ASC)
    ├── MovementSubsystem.apply_orders()     → update MovementStates
    │   Handles: MOVE_TO, RTB, HOLD, SET_SPEED, PATROL, ABORT
    └── [Phase 2+] ProductionSubsystem, IntelSubsystem, etc.

 3. SUBSYSTEM EXECUTION  (strict ordering — DO NOT reorder without updating this doc)
    ├── 3a. MovementSubsystem.resolve_tick() → new positions, waypoint events
    ├── 3b. FuelSubsystem.resolve_tick()     → fuel burn, LOW/BINGO alerts, RTB orders
    ├── 3c. RTB order re-injection           → BINGO RTB orders fed back into movement
    │   [Phase 2 hooks will slot in here:]
    ├── 3d. [CombatSubsystem]                → detection, engagement resolution
    ├── 3e. [MaintenanceSubsystem]           → maintenance timers
    └── 3f. [ProductionSubsystem]            → DIB delivery

 4. STATE WRITE
    ├── StateManager.flush_dirty()           → Redis HMSET pipeline (all dirty platforms)
    ├── StateManager.save_movement_states()  → Redis pipeline (dirty movement states)
    ├── StateManager.update_game_tick()      → Redis + DB tick counter
    └── [every DB_FLUSH_EVERY_N_TICKS] DB batch upsert of platform rows

 5. EVENT EMISSION
    ├── EventBus.publish_many()              → Redis Stream
    └── WebSocket broadcast (caller: AsyncTickRunner)
        ├── tick event: { tick, paused: false }
        └── platform_updates: [ PlatformDelta, ... ]  (only changed platforms, delta-only)

═══════════════════════════════════════════════════════════════════════════════
FUTURE COMBAT HOOK POINTS
═══════════════════════════════════════════════════════════════════════════════

Phase 3 (Combat Simulation) will slot into step 3d above.  The CombatSubsystem
will receive the same `platforms` dict and the current `movement_states`, plus
an `IntelligenceState` object populated by ISR assets.  It will:
  - Run detection pass (radar/sonar range checks → IntelligenceTrack creation)
  - Run engagement resolver (PK tables, intercept geometry)
  - Emit ENGAGEMENT / HIT / MISS / DESTRUCTION events
  - Modify platform health/status in the same `platforms` dict

No changes to the TickEngine lifecycle are required — combat plugs in cleanly.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from redis.asyncio import Redis

from .event_bus import EventBus
from .models import (
    OrderPriority,
    OrderType,
    PlatformDelta,
    PlatformHotState,
    SimEvent,
    SimEventType,
    TickResult,
)
from .order_queue import OrderQueue
from .state_manager import StateManager
from .subsystems.fuel import FuelSubsystem
from .subsystems.movement import MovementSubsystem

log = logging.getLogger(__name__)


class TickEngine:
    """
    Executes one deterministic game-tick for a single game session.

    All state mutations happen to in-memory PlatformHotState dicts.
    The StateManager handles all I/O (Redis + DB) before and after.

    Thread safety: each game has its own TickEngine instance; no shared
    mutable state between games.
    """

    def __init__(self, game_id: str, redis: Redis) -> None:
        self._game_id = game_id
        self._redis = redis

        self._state_manager = StateManager(redis)
        self._event_bus = EventBus(redis)
        self._order_queue = OrderQueue(redis)

        self._movement = MovementSubsystem()
        self._fuel = FuelSubsystem(game_id)

    # ── Public interface ──────────────────────────────────────────────────────

    async def run_tick(self, tick: int) -> TickResult:
        """
        Execute one full tick.  Returns TickResult summarising what happened.
        The caller (AsyncTickRunner) uses the result to broadcast WebSocket updates.

        This method is not re-entrant.  The AsyncTickRunner guarantees only
        one tick runs at a time per game.
        """
        wall_start = time.monotonic()
        all_deltas: list[PlatformDelta] = []
        all_events: list[SimEvent] = []
        warnings: list[str] = []

        # ── 1. LOAD ───────────────────────────────────────────────────────────
        try:
            platforms = await self._state_manager.load_game_platforms(self._game_id)
        except Exception as exc:
            log.error("TICK %d | LOAD FAILED for %s: %s", tick, self._game_id, exc)
            return self._error_result(tick, wall_start, str(exc))

        if not platforms:
            log.debug("TICK %d | no platforms for game %s", tick, self._game_id)
            await self._state_manager.update_game_tick(self._game_id, tick)
            return TickResult(
                game_id=self._game_id,
                tick=tick,
                wall_ms=(time.monotonic() - wall_start) * 1000,
                platforms_processed=0,
                platforms_moved=0,
                platforms_rtb_triggered=0,
                deltas=[],
                events=[],
            )

        moving_platform_ids = list(platforms.keys())
        movement_states = await self._state_manager.load_movement_states(moving_platform_ids)
        orders = await self._order_queue.pop_all(self._game_id)

        log.debug(
            "TICK %d | game=%s platforms=%d orders=%d",
            tick, self._game_id, len(platforms), len(orders),
        )

        # ── 2. ORDER RESOLUTION ───────────────────────────────────────────────
        # Orders are already sorted by score (priority ASC, submission_tick ASC)
        # from ZPOPMIN.  Apply movement orders first.
        movement_orders = [o for o in orders if o.order_type in (
            OrderType.MOVE_TO, OrderType.RTB, OrderType.HOLD,
            OrderType.SET_SPEED, OrderType.PATROL, OrderType.ABORT,
        )]

        order_events = self._movement.apply_orders(
            platforms, movement_orders, movement_states, tick
        )
        all_events.extend(order_events)

        # ── 3a. MOVEMENT ──────────────────────────────────────────────────────
        mov_result = self._movement.resolve_tick(platforms, movement_states, tick)
        all_deltas.extend(mov_result.deltas)
        all_events.extend(mov_result.events)

        # Persist changed movement states immediately (before fuel alters status)
        if mov_result.dirty_movement_states:
            await self._state_manager.save_movement_states_batch(
                mov_result.dirty_movement_states
            )

        # ── 3b. FUEL ──────────────────────────────────────────────────────────
        fuel_result = self._fuel.resolve_tick(platforms, tick)
        all_events.extend(fuel_result.events)

        # Merge fuel deltas: if a platform already has a movement delta,
        # append fuel_state to it; otherwise create a new delta.
        existing_delta_map: dict[str, PlatformDelta] = {d.id: d for d in all_deltas}
        for fd in fuel_result.deltas:
            if fd.id in existing_delta_map:
                existing_delta_map[fd.id].fuel_state = fd.fuel_state
            else:
                existing_delta_map[fd.id] = fd
                all_deltas.append(fd)

        # ── 3c. RTB ORDER RE-INJECTION ────────────────────────────────────────
        # BINGO-triggered RTB orders are fed back through the movement subsystem
        # immediately (same tick) so platforms begin returning without one-tick delay.
        if fuel_result.rtb_orders:
            rtb_apply_events = self._movement.apply_orders(
                platforms, fuel_result.rtb_orders, movement_states, tick
            )
            all_events.extend(rtb_apply_events)

        # ── [3d–3f PHASE 2+ HOOKS SLOT IN HERE] ──────────────────────────────

        # ── 4. STATE WRITE ────────────────────────────────────────────────────
        dirty_count = await self._state_manager.flush_dirty(platforms, tick)
        await self._state_manager.update_game_tick(self._game_id, tick)

        # ── 5. EVENT EMISSION ─────────────────────────────────────────────────
        await self._event_bus.publish_many(self._game_id, all_events)

        wall_ms = (time.monotonic() - wall_start) * 1000

        if wall_ms > 500:
            warnings.append(
                f"Tick {tick} took {wall_ms:.0f}ms — exceeds 500ms budget "
                f"({len(platforms)} platforms)"
            )
            log.warning(warnings[-1])

        log.debug(
            "TICK %d | moved=%d fuel_burned=%d events=%d dirty=%d wall=%.1fms",
            tick,
            mov_result.moved_count,
            fuel_result.platforms_burned,
            len(all_events),
            dirty_count,
            wall_ms,
        )

        return TickResult(
            game_id=self._game_id,
            tick=tick,
            wall_ms=wall_ms,
            platforms_processed=len(platforms),
            platforms_moved=mov_result.moved_count,
            platforms_rtb_triggered=fuel_result.platforms_bingo,
            deltas=all_deltas,
            events=all_events,
            warnings=warnings,
        )

    async def teardown(self) -> None:
        """Called by AsyncTickRunner when game stops.  Clean up per-game state."""
        await self._state_manager.unregister_game(self._game_id)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _error_result(self, tick: int, wall_start: float, error: str) -> TickResult:
        return TickResult(
            game_id=self._game_id,
            tick=tick,
            wall_ms=(time.monotonic() - wall_start) * 1000,
            platforms_processed=0,
            platforms_moved=0,
            platforms_rtb_triggered=0,
            deltas=[],
            events=[],
            warnings=[f"TICK ERROR: {error}"],
        )
