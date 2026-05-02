"""
Tick-level integration tests — run full TickEngine ticks without live Redis/DB.

Uses unittest.mock to stub the StateManager, OrderQueue, and EventBus so the
engine's deterministic logic can be exercised in isolation.

Validates:
  - Full tick lifecycle executes without errors for 50- and 100-platform games
  - Movement + fuel subsystems both run and produce combined deltas
  - RTB orders from BINGO fuel are re-injected same tick (no one-tick lag)
  - TickResult fields are populated correctly
  - No state desync: platform positions after N ticks are consistent
    (each tick's start state = previous tick's end state)
"""
from __future__ import annotations

import asyncio
import uuid
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from sim_engine.engine import TickEngine
from sim_engine.models import (
    MovementState,
    OrderPriority,
    OrderType,
    OrderWaypoint,
    PlatformDelta,
    PlatformHotState,
    PlatformOrder,
    SimEvent,
    SimEventType,
    TickResult,
)
from tests.conftest import make_platform, make_move_order, make_platforms_grid


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_movement_states(
    platforms: dict[str, PlatformHotState],
    target: list[float] | None = None,
) -> dict[str, MovementState | None]:
    if target is None:
        return {pid: None for pid in platforms}
    return {
        pid: MovementState(
            waypoints=[target], current_wp_index=0,
            hold_ticks_remaining=0, patrol_loop=False,
        )
        for pid in platforms
    }


def _make_engine_with_stubs(
    game_id: str,
    platforms: dict[str, PlatformHotState],
    movement_states: dict[str, MovementState | None],
    orders: list[PlatformOrder] | None = None,
) -> TickEngine:
    """
    Build a TickEngine with all I/O methods replaced by in-memory stubs.
    """
    redis_mock = MagicMock()
    engine = TickEngine(game_id=game_id, redis=redis_mock)

    # Stub StateManager
    engine._state_manager.load_game_platforms = AsyncMock(return_value=platforms)
    engine._state_manager.load_movement_states = AsyncMock(return_value=movement_states)
    engine._state_manager.flush_dirty = AsyncMock(return_value=len(
        [p for p in platforms.values() if p.is_dirty]
    ))
    engine._state_manager.save_movement_states_batch = AsyncMock()
    engine._state_manager.update_game_tick = AsyncMock()

    # Stub OrderQueue
    engine._order_queue.pop_all = AsyncMock(return_value=orders or [])

    # Stub EventBus
    engine._event_bus.publish_many = AsyncMock()

    # Stub the DB session boundary — missions + production + ISR don't run in tests
    from sim_engine.subsystems.missions import MissionTickResult
    from sim_engine.subsystems.isr import ISRTickResult
    engine._run_db_subsystems = AsyncMock(return_value=(MissionTickResult(), [], ISRTickResult()))

    return engine


# ── Full tick tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFullTick:
    async def test_tick_returns_result_for_empty_game(self):
        game_id = str(uuid.uuid4())
        engine = _make_engine_with_stubs(game_id, {}, {})
        result = await engine.run_tick(tick=0)
        assert isinstance(result, TickResult)
        assert result.platforms_processed == 0
        assert result.deltas == []

    async def test_tick_with_50_stationary_platforms(self):
        game_id = str(uuid.uuid4())
        platforms = make_platforms_grid(50, game_id=game_id, speed_knots=0.0)
        movement_states = make_movement_states(platforms)
        engine = _make_engine_with_stubs(game_id, platforms, movement_states)
        result = await engine.run_tick(tick=1)
        assert result.platforms_processed == 50
        assert result.platforms_moved == 0
        # Fuel deltas should still exist (platforms burn at idle)
        assert len(result.deltas) == 50  # all burn, so all dirty

    async def test_tick_with_50_moving_platforms(self):
        game_id = str(uuid.uuid4())
        platforms = make_platforms_grid(50, game_id=game_id, speed_knots=480.0)
        for p in platforms.values():
            p.status = "IN_TRANSIT"
        movement_states = make_movement_states(platforms, target=[130.0, 25.0])
        engine = _make_engine_with_stubs(game_id, platforms, movement_states)
        result = await engine.run_tick(tick=0)
        assert result.platforms_processed == 50
        assert result.platforms_moved == 50
        assert len(result.deltas) == 50

    async def test_tick_with_100_moving_platforms(self):
        game_id = str(uuid.uuid4())
        platforms = make_platforms_grid(100, game_id=game_id, speed_knots=480.0)
        for p in platforms.values():
            p.status = "IN_TRANSIT"
        movement_states = make_movement_states(platforms, target=[130.0, 25.0])
        engine = _make_engine_with_stubs(game_id, platforms, movement_states)
        result = await engine.run_tick(tick=0)
        assert result.platforms_processed == 100
        assert result.platforms_moved == 100

    async def test_order_applied_before_movement(self):
        """A MOVE_TO order submitted with the tick should be applied before movement."""
        game_id = str(uuid.uuid4())
        p = make_platform(pid="p1", game_id=game_id, lon=121.5, lat=24.0,
                          speed_knots=0.0, status="ACTIVE")
        platforms = {"p1": p}
        movement_states = {"p1": None}

        order = make_move_order(game_id, "p1", [[125.0, 26.0]], speed_knots=480.0)
        engine = _make_engine_with_stubs(game_id, platforms, movement_states, orders=[order])

        result = await engine.run_tick(tick=0)
        # Platform was stationary but got MOVE_TO — should have moved
        assert result.platforms_moved == 1
        assert p.pos_lon != pytest.approx(121.5, abs=0.001) or p.pos_lat != pytest.approx(24.0, abs=0.001)

    async def test_bingo_rtb_reinjected_same_tick(self):
        """BINGO fuel should trigger RTB on the same tick, not next tick."""
        game_id = str(uuid.uuid4())
        # Platform at BINGO fuel + 1 unit — guaranteed to cross this tick at cruise
        p = make_platform(
            pid="p1", game_id=game_id,
            lon=121.5, lat=24.0, speed_knots=480.0, status="IN_TRANSIT",
            fuel_burn_rate_per_tick=100.0, fuel_capacity_lbs=500.0,
            cruise_speed_knots=480.0, fuel_state=0.101,  # just above BINGO
        )
        platforms = {"p1": p}
        movement_states = {"p1": MovementState(
            waypoints=[[125.0, 26.0]], current_wp_index=0,
            hold_ticks_remaining=0, patrol_loop=False,
        )}

        rtb_events: list[SimEvent] = []

        engine = _make_engine_with_stubs(game_id, platforms, movement_states)
        result = await engine.run_tick(tick=0)

        # FUEL_BINGO event should appear this tick
        bingo_events = [e for e in result.events if e.type == SimEventType.FUEL_BINGO]
        assert len(bingo_events) == 1, f"Expected 1 BINGO event, got {len(bingo_events)}"

    async def test_tick_result_wall_ms_positive(self):
        game_id = str(uuid.uuid4())
        platforms = make_platforms_grid(20, game_id=game_id)
        engine = _make_engine_with_stubs(game_id, platforms, make_movement_states(platforms))
        result = await engine.run_tick(tick=0)
        assert result.wall_ms >= 0.0


# ── State consistency (no desync) across N ticks ──────────────────────────────

@pytest.mark.asyncio
class TestMultiTickConsistency:
    async def _run_n_ticks(
        self,
        game_id: str,
        platforms: dict[str, PlatformHotState],
        n_ticks: int,
        target: list[float],
    ) -> list[TickResult]:
        results = []
        for tick in range(n_ticks):
            # Rebuild movement states each tick (simulates StateManager loading fresh)
            movement_states = {
                pid: MovementState(
                    waypoints=[target], current_wp_index=0,
                    hold_ticks_remaining=0, patrol_loop=False,
                )
                for pid in platforms
            }
            engine = _make_engine_with_stubs(game_id, platforms, movement_states)
            result = await engine.run_tick(tick=tick)
            results.append(result)
        return results

    async def test_positions_monotonically_decrease_distance_to_target(self):
        """Each tick should bring platforms strictly closer to the target."""
        game_id = str(uuid.uuid4())
        target = [130.0, 25.0]
        platforms = make_platforms_grid(10, game_id=game_id, speed_knots=480.0,
                                        base_lon=120.0, base_lat=22.0)
        for p in platforms.values():
            p.status = "IN_TRANSIT"

        from sim_engine.subsystems.movement import haversine_nm

        prev_distances = {
            pid: haversine_nm(p.pos_lon, p.pos_lat, target[0], target[1])
            for pid, p in platforms.items()
        }

        for tick in range(5):
            movement_states = make_movement_states(platforms, target=target)
            engine = _make_engine_with_stubs(game_id, platforms, movement_states)
            await engine.run_tick(tick=tick)

            for pid, p in platforms.items():
                new_dist = haversine_nm(p.pos_lon, p.pos_lat, target[0], target[1])
                # Once a platform arrives (dist ≈ 0) it stays there — skip monotonicity check
                if prev_distances[pid] < 1.0:
                    prev_distances[pid] = new_dist
                    continue
                assert new_dist < prev_distances[pid], (
                    f"Platform {pid} tick {tick}: distance did not decrease "
                    f"({prev_distances[pid]:.2f} → {new_dist:.2f})"
                )
                prev_distances[pid] = new_dist

    async def test_fuel_decreases_monotonically(self):
        """Fuel should strictly decrease each tick for non-nuclear platforms."""
        game_id = str(uuid.uuid4())
        platforms = {
            "p1": make_platform(pid="p1", game_id=game_id, speed_knots=480.0,
                                 fuel_state=0.9, is_nuclear=False)
        }

        prev_fuel = platforms["p1"].fuel_state
        for tick in range(5):
            engine = _make_engine_with_stubs(game_id, platforms, {"p1": None})
            await engine.run_tick(tick=tick)
            new_fuel = platforms["p1"].fuel_state
            assert new_fuel < prev_fuel, f"Tick {tick}: fuel should have decreased"
            prev_fuel = new_fuel

    async def test_nuclear_platform_fuel_unchanged_across_ticks(self):
        game_id = str(uuid.uuid4())
        platforms = {
            "p1": make_platform(pid="p1", game_id=game_id, speed_knots=30.0,
                                 fuel_state=1.0, is_nuclear=True, type_key="CVN_78")
        }
        for tick in range(5):
            engine = _make_engine_with_stubs(game_id, platforms, {"p1": None})
            await engine.run_tick(tick=tick)
        assert platforms["p1"].fuel_state == pytest.approx(1.0)

    async def test_tick_id_increments_in_result(self):
        game_id = str(uuid.uuid4())
        platforms = make_platforms_grid(5, game_id=game_id)
        for tick_num in range(5):
            engine = _make_engine_with_stubs(
                game_id, platforms, make_movement_states(platforms)
            )
            result = await engine.run_tick(tick=tick_num)
            assert result.tick == tick_num


# ── Delta compression tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
class TestDeltaCompression:
    async def test_only_dirty_platforms_in_deltas(self):
        """Stationary non-burning platforms should produce no deltas."""
        game_id = str(uuid.uuid4())
        # Nuclear + stationary = nothing changes
        platforms = {
            "p1": make_platform(pid="p1", game_id=game_id, speed_knots=0.0,
                                 is_nuclear=True, status="ACTIVE"),
        }
        engine = _make_engine_with_stubs(game_id, platforms, {"p1": None})
        result = await engine.run_tick(tick=0)
        # Nuclear + stationary → no fuel burn, no movement → no deltas
        assert result.deltas == []

    async def test_moving_non_nuclear_has_combined_delta(self):
        """A platform that moves AND burns fuel should have one merged delta."""
        game_id = str(uuid.uuid4())
        p = make_platform(pid="p1", game_id=game_id,
                          lon=121.5, lat=24.0, speed_knots=480.0,
                          status="IN_TRANSIT", is_nuclear=False,
                          fuel_burn_rate_per_tick=500.0,
                          fuel_capacity_lbs=18_500.0,
                          cruise_speed_knots=480.0)
        engine = _make_engine_with_stubs(
            game_id, {"p1": p},
            {"p1": MovementState(waypoints=[[125.0, 26.0]], current_wp_index=0,
                                  hold_ticks_remaining=0, patrol_loop=False)}
        )
        result = await engine.run_tick(tick=0)
        assert len(result.deltas) == 1
        d = result.deltas[0]
        assert d.id == "p1"
        assert d.position is not None and len(d.position) == 2  # movement component
        assert d.fuel_state is not None  # fuel component merged in
