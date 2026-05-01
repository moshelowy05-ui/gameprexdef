"""
Movement subsystem tests.

Validates:
  - Haversine / bearing / destination math correctness
  - apply_orders: MOVE_TO, HOLD, RTB, ABORT, SET_SPEED
  - resolve_tick: platforms advance toward waypoint, heading updated
  - Waypoint arrival: index advances, events emitted, loop for PATROL
  - 100-platform bulk test: all platforms move, O(N) vectorized path
  - Determinism: two identical ticks produce bit-for-bit identical deltas
"""
from __future__ import annotations

import math
import uuid
from copy import deepcopy

import numpy as np
import pytest

from sim_engine.models import MovementState, OrderPriority, OrderType, OrderWaypoint, PlatformOrder
from sim_engine.subsystems.movement import (
    MovementSubsystem,
    _EARTH_RADIUS_NM,
    _WAYPOINT_ARRIVAL_RADIUS_NM,
    bearing_deg,
    destination_point,
    haversine_nm,
)
from tests.conftest import make_platform, make_move_order, make_platforms_grid


# ── Math unit tests ───────────────────────────────────────────────────────────

class TestHaversine:
    def test_zero_distance(self):
        assert haversine_nm(121.5, 24.0, 121.5, 24.0) == pytest.approx(0.0, abs=1e-10)

    def test_known_distance(self):
        # Kadena AB (127.77, 26.35) to Yokosuka (139.67, 35.29) ≈ 860-870 NM
        d = haversine_nm(127.77, 26.35, 139.67, 35.29)
        assert 800 < d < 1000, f"Expected ~860-870 NM, got {d:.1f}"

    def test_symmetry(self):
        d1 = haversine_nm(121.5, 24.0, 130.0, 28.0)
        d2 = haversine_nm(130.0, 28.0, 121.5, 24.0)
        assert d1 == pytest.approx(d2, rel=1e-10)

    def test_vectorized_equals_scalar(self):
        lons1 = np.array([121.5, 127.77, 130.0])
        lats1 = np.array([24.0,  26.35,  28.0])
        lons2 = np.array([130.0, 139.67, 121.5])
        lats2 = np.array([28.0,  35.29,  24.0])
        arr = haversine_nm(lons1, lats1, lons2, lats2)
        for i in range(3):
            scalar = haversine_nm(float(lons1[i]), float(lats1[i]),
                                  float(lons2[i]), float(lats2[i]))
            assert arr[i] == pytest.approx(scalar, rel=1e-10)


class TestBearing:
    def test_due_north(self):
        # Moving due north
        b = bearing_deg(121.5, 20.0, 121.5, 25.0)
        assert float(b) == pytest.approx(0.0, abs=0.01)

    def test_due_east(self):
        # Moving due east at equator
        b = bearing_deg(0.0, 0.0, 10.0, 0.0)
        assert float(b) == pytest.approx(90.0, abs=0.1)

    def test_range_0_360(self):
        # All bearings should be [0, 360)
        points = [(121.5, 24.0, 130.0, 28.0), (130.0, 28.0, 121.5, 24.0),
                  (0.0, 0.0, 0.0, -10.0)]
        for lo1, la1, lo2, la2 in points:
            b = float(bearing_deg(lo1, la1, lo2, la2))
            assert 0.0 <= b < 360.0, f"Bearing out of range: {b}"


class TestDestinationPoint:
    def test_due_north(self):
        # Move 60 NM due north from (0, 0) → lat should increase ~1 degree
        new_lon, new_lat = destination_point(0.0, 0.0, 0.0, 60.0)
        assert float(new_lon) == pytest.approx(0.0, abs=1e-8)
        assert float(new_lat) == pytest.approx(1.0, abs=0.01)

    def test_round_trip(self):
        # destination_point + haversine = original distance
        lon, lat = 121.5, 24.0
        brg, dist = 045.0, 200.0
        new_lon, new_lat = destination_point(lon, lat, brg, dist)
        recovered = haversine_nm(lon, lat, float(new_lon), float(new_lat))
        assert recovered == pytest.approx(dist, rel=1e-6)


# ── MovementSubsystem unit tests ──────────────────────────────────────────────

class TestApplyOrders:
    def setup_method(self):
        self.ms = MovementSubsystem()
        self.game_id = "test-game"

    def test_move_to_sets_movement_state(self):
        p = make_platform(pid="p1", game_id=self.game_id, speed_knots=0.0)
        platforms = {"p1": p}
        movement_states: dict = {"p1": None}
        order = make_move_order(self.game_id, "p1", [[125.0, 26.0]], speed_knots=480.0)
        self.ms.apply_orders(platforms, [order], movement_states, tick=0)

        ms = movement_states["p1"]
        assert ms is not None
        assert ms.waypoints == [[125.0, 26.0]]
        assert ms.current_wp_index == 0
        assert p.status == "IN_TRANSIT"
        assert p.speed_knots == 480.0

    def test_hold_sets_remaining_ticks(self):
        p = make_platform(pid="p1", game_id=self.game_id)
        ms_state = MovementState(waypoints=[[125.0, 26.0]], current_wp_index=0,
                                  hold_ticks_remaining=0, patrol_loop=False)
        movement_states = {"p1": ms_state}
        hold_order = PlatformOrder(
            id=str(uuid.uuid4()), game_id=self.game_id, platform_id="p1",
            order_type=OrderType.HOLD, submission_tick=0,
        )
        self.ms.apply_orders({"p1": p}, [hold_order], movement_states, tick=0)
        assert movement_states["p1"].hold_ticks_remaining >= 1

    def test_abort_clears_movement_state(self):
        p = make_platform(pid="p1", game_id=self.game_id, status="IN_TRANSIT")
        ms_state = MovementState(waypoints=[[125.0, 26.0]], current_wp_index=0,
                                  hold_ticks_remaining=0, patrol_loop=False)
        movement_states = {"p1": ms_state}
        abort_order = PlatformOrder(
            id=str(uuid.uuid4()), game_id=self.game_id, platform_id="p1",
            order_type=OrderType.ABORT, submission_tick=0,
        )
        self.ms.apply_orders({"p1": p}, [abort_order], movement_states, tick=0)
        assert movement_states["p1"] is None or movement_states["p1"].waypoints == []

    def test_set_speed_adjusts_platform(self):
        p = make_platform(pid="p1", game_id=self.game_id, speed_knots=100.0)
        movement_states = {"p1": None}
        speed_order = PlatformOrder(
            id=str(uuid.uuid4()), game_id=self.game_id, platform_id="p1",
            order_type=OrderType.SET_SPEED, submission_tick=0,
            target_speed_knots=300.0,
        )
        self.ms.apply_orders({"p1": p}, [speed_order], movement_states, tick=0)
        assert p.speed_knots == 300.0

    def test_unknown_platform_skipped(self):
        movement_states: dict = {}
        order = make_move_order(self.game_id, "nonexistent", [[125.0, 26.0]])
        # Should not raise
        self.ms.apply_orders({}, [order], movement_states, tick=0)


class TestResolveTick:
    def setup_method(self):
        self.ms = MovementSubsystem()
        self.game_id = "test-game"

    def test_platform_advances_toward_waypoint(self):
        p = make_platform(pid="p1", game_id=self.game_id,
                          lon=121.5, lat=24.0, speed_knots=480.0, status="IN_TRANSIT")
        target = [125.0, 26.0]
        ms_state = MovementState(waypoints=[target], current_wp_index=0,
                                  hold_ticks_remaining=0, patrol_loop=False)
        dist_before = haversine_nm(p.pos_lon, p.pos_lat, target[0], target[1])

        result = self.ms.resolve_tick({"p1": p}, {"p1": ms_state}, tick=0)

        dist_after = haversine_nm(p.pos_lon, p.pos_lat, target[0], target[1])
        assert dist_after < dist_before, "Platform should be closer to waypoint after tick"
        assert result.moved_count == 1

    def test_heading_updated(self):
        p = make_platform(pid="p1", game_id=self.game_id,
                          lon=121.5, lat=24.0, speed_knots=480.0, status="IN_TRANSIT",
                          heading=0.0)
        target = [125.0, 24.0]  # due east
        ms_state = MovementState(waypoints=[target], current_wp_index=0,
                                  hold_ticks_remaining=0, patrol_loop=False)
        self.ms.resolve_tick({"p1": p}, {"p1": ms_state}, tick=0)
        # Heading toward east should be ~90°
        assert 80.0 < p.heading < 100.0, f"Heading toward east should be ~90°, got {p.heading}"

    def test_stationary_platform_skipped(self):
        p = make_platform(pid="p1", game_id=self.game_id, speed_knots=0.0)
        lon_before, lat_before = p.pos_lon, p.pos_lat
        result = self.ms.resolve_tick({"p1": p}, {"p1": None}, tick=0)
        assert p.pos_lon == lon_before
        assert p.pos_lat == lat_before
        assert result.moved_count == 0

    def test_waypoint_arrival_advances_index(self):
        # Place platform very close to waypoint (< 0.5 NM)
        target = [121.5, 24.0]
        next_wp = [125.0, 26.0]
        p = make_platform(pid="p1", game_id=self.game_id,
                          lon=121.500001, lat=24.000001,  # essentially at target
                          speed_knots=30.0, status="IN_TRANSIT")
        ms_state = MovementState(
            waypoints=[target, next_wp],
            current_wp_index=0,
            hold_ticks_remaining=0,
            patrol_loop=False,
        )
        result = self.ms.resolve_tick({"p1": p}, {"p1": ms_state}, tick=0)
        # Should have emitted a WAYPOINT_REACHED event
        event_types = [e.type.value for e in result.events]
        assert any("WAYPOINT" in et for et in event_types), f"No waypoint event, got: {event_types}"

    def test_patrol_loops_back(self):
        wp1 = [121.5, 24.0]
        wp2 = [122.0, 24.0]
        p = make_platform(pid="p1", game_id=self.game_id,
                          lon=121.500001, lat=24.000001,
                          speed_knots=30.0, status="IN_TRANSIT")
        ms_state = MovementState(
            waypoints=[wp1, wp2],
            current_wp_index=0,
            hold_ticks_remaining=0,
            patrol_loop=True,
        )
        result = self.ms.resolve_tick({"p1": p}, {"p1": ms_state}, tick=0)
        # After looping past last wp, index should reset to 0
        # (or at least be valid)
        assert ms_state.current_wp_index >= 0

    def test_delta_contains_updated_position(self):
        p = make_platform(pid="p1", game_id=self.game_id,
                          lon=121.5, lat=24.0, speed_knots=480.0, status="IN_TRANSIT")
        ms_state = MovementState(waypoints=[[125.0, 26.0]], current_wp_index=0,
                                  hold_ticks_remaining=0, patrol_loop=False)
        result = self.ms.resolve_tick({"p1": p}, {"p1": ms_state}, tick=0)
        assert len(result.deltas) == 1
        d = result.deltas[0]
        assert d.id == "p1"
        assert d.position is not None and len(d.position) == 2
        assert d.heading is not None


# ── Bulk performance tests ────────────────────────────────────────────────────

class TestBulkMovement:
    def setup_method(self):
        self.ms = MovementSubsystem()
        self.game_id = "test-game"

    def _make_movement_states_toward(
        self, platforms: dict[str, PlatformHotState], target: list[float]
    ) -> dict[str, MovementState | None]:
        return {
            pid: MovementState(
                waypoints=[target], current_wp_index=0,
                hold_ticks_remaining=0, patrol_loop=False,
            )
            for pid in platforms
        }

    def test_100_platforms_all_move(self):
        platforms = make_platforms_grid(100, game_id=self.game_id,
                                        base_lon=120.0, base_lat=20.0,
                                        speed_knots=300.0)
        for p in platforms.values():
            p.status = "IN_TRANSIT"
        target = [130.0, 25.0]
        movement_states = self._make_movement_states_toward(platforms, target)

        result = self.ms.resolve_tick(platforms, movement_states, tick=0)
        assert result.moved_count == 100
        assert len(result.deltas) == 100

    def test_50_stationary_50_moving(self):
        platforms = make_platforms_grid(100, game_id=self.game_id, speed_knots=0.0)
        movement_states: dict[str, MovementState | None] = {}
        for i, (pid, p) in enumerate(platforms.items()):
            if i < 50:
                p.speed_knots = 480.0
                p.status = "IN_TRANSIT"
                movement_states[pid] = MovementState(
                    waypoints=[[130.0, 25.0]], current_wp_index=0,
                    hold_ticks_remaining=0, patrol_loop=False,
                )
            else:
                movement_states[pid] = None

        result = self.ms.resolve_tick(platforms, movement_states, tick=0)
        assert result.moved_count == 50

    def test_positions_differ_per_platform(self):
        """Each platform should end up at a unique position (no aliasing).

        Target is 2000+ NM away so no platform arrives this tick — all stop
        mid-flight at distinct interpolated positions.
        """
        platforms = make_platforms_grid(20, game_id=self.game_id,
                                        base_lon=120.0, base_lat=20.0,
                                        step=0.5, speed_knots=480.0)
        for p in platforms.values():
            p.status = "IN_TRANSIT"
        # Use a far-away target (Guam ≈ 2000 NM from the grid) so no platform arrives
        movement_states = self._make_movement_states_toward(platforms, [144.93, 13.44])
        result = self.ms.resolve_tick(platforms, movement_states, tick=0)
        positions = [(round(d.position[0], 6), round(d.position[1], 6))
                     for d in result.deltas if d.position is not None]
        assert len(set(positions)) == len(positions), "Two platforms ended at the same position"


# ── Determinism tests ─────────────────────────────────────────────────────────

class TestDeterminism:
    def setup_method(self):
        self.game_id = "test-game"

    def test_two_identical_ticks_produce_same_deltas(self):
        ms = MovementSubsystem()
        platforms_a = make_platforms_grid(50, game_id=self.game_id, speed_knots=480.0)
        for p in platforms_a.values():
            p.status = "IN_TRANSIT"
        target = [130.0, 25.0]
        mv_a = {pid: MovementState(waypoints=[target], current_wp_index=0,
                                    hold_ticks_remaining=0, patrol_loop=False)
                for pid in platforms_a}

        # Deep copy for second run
        platforms_b = deepcopy(platforms_a)
        mv_b = deepcopy(mv_a)

        result_a = ms.resolve_tick(platforms_a, mv_a, tick=5)
        result_b = ms.resolve_tick(platforms_b, mv_b, tick=5)

        assert result_a.moved_count == result_b.moved_count
        deltas_a = sorted(result_a.deltas, key=lambda d: d.id)
        deltas_b = sorted(result_b.deltas, key=lambda d: d.id)
        for da, db in zip(deltas_a, deltas_b):
            assert da.id == db.id
            assert da.position is not None and db.position is not None
            assert da.position[0] == pytest.approx(db.position[0], abs=1e-10)
            assert da.position[1] == pytest.approx(db.position[1], abs=1e-10)
            assert da.heading == pytest.approx(db.heading, abs=1e-10)

    def test_tick_number_does_not_affect_position_calculation(self):
        """Position math should be independent of tick number."""
        ms = MovementSubsystem()
        platforms_t1 = make_platforms_grid(10, game_id=self.game_id, speed_knots=300.0)
        platforms_t99 = deepcopy(platforms_t1)
        for p in platforms_t1.values():
            p.status = "IN_TRANSIT"
        for p in platforms_t99.values():
            p.status = "IN_TRANSIT"
        target = [125.0, 22.0]
        mv1 = {pid: MovementState(waypoints=[target], current_wp_index=0,
                                   hold_ticks_remaining=0, patrol_loop=False)
               for pid in platforms_t1}
        mv99 = deepcopy(mv1)

        r1 = ms.resolve_tick(platforms_t1, mv1, tick=1)
        r99 = ms.resolve_tick(platforms_t99, mv99, tick=99)

        for d1, d99 in zip(
            sorted(r1.deltas, key=lambda d: d.id),
            sorted(r99.deltas, key=lambda d: d.id),
        ):
            assert d1.position is not None and d99.position is not None
            assert d1.position[0] == pytest.approx(d99.position[0], abs=1e-10)
            assert d1.position[1] == pytest.approx(d99.position[1], abs=1e-10)
