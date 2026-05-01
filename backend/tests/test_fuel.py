"""
Fuel subsystem tests.

Validates:
  - Burn rate math: idle, cruise, above-cruise
  - LOW_FUEL alert fires exactly once when crossing 20%
  - BINGO alert fires exactly once when crossing 10%; RTB order generated
  - EXHAUSTED: airborne → DESTROYED; surface → stays ACTIVE
  - Nuclear platforms never burn fuel
  - Platforms in DESTROYED/RETIRED/IN_PRODUCTION skipped
  - 100-platform bulk test: all eligible platforms lose fuel each tick
  - BINGO suppression: repeated ticks don't re-fire
"""
from __future__ import annotations

import pytest

from sim_engine.models import SimEventType
from sim_engine.subsystems.fuel import (
    BINGO_FUEL_THRESHOLD,
    EXHAUSTED_THRESHOLD,
    IDLE_BURN_FRACTION,
    LOW_FUEL_THRESHOLD,
    SPEED_BURN_EXPONENT,
    FuelSubsystem,
)
from tests.conftest import make_platform, make_platforms_grid


# ── Burn rate unit tests ──────────────────────────────────────────────────────

class TestBurnRateMath:
    def test_stationary_burns_idle_fraction(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=0.0,
                          fuel_burn_rate_per_tick=1000.0, fuel_capacity_lbs=10_000.0,
                          cruise_speed_knots=500.0, fuel_state=1.0)
        result = fs.resolve_tick({"p1": p}, tick=0)
        # Expected burn = 1000 * 0.15 = 150 lbs → Δstate = 150/10000 = 0.015
        expected_state = 1.0 - 0.015
        assert p.fuel_state == pytest.approx(expected_state, rel=1e-6)

    def test_cruise_speed_burns_at_full_rate(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=500.0,
                          fuel_burn_rate_per_tick=1000.0, fuel_capacity_lbs=10_000.0,
                          cruise_speed_knots=500.0, fuel_state=1.0)
        result = fs.resolve_tick({"p1": p}, tick=0)
        # speed_ratio = 1.0, modifier = 1.0^1.5 = 1.0, burn = 1000
        expected_state = 1.0 - (1000.0 / 10_000.0)
        assert p.fuel_state == pytest.approx(expected_state, rel=1e-6)

    def test_half_speed_burns_less(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=250.0,
                          fuel_burn_rate_per_tick=1000.0, fuel_capacity_lbs=10_000.0,
                          cruise_speed_knots=500.0, fuel_state=1.0)
        result = fs.resolve_tick({"p1": p}, tick=0)
        # modifier = (0.5)^1.5 ≈ 0.3536
        expected_modifier = (0.5) ** SPEED_BURN_EXPONENT
        expected_state = 1.0 - (1000.0 * expected_modifier / 10_000.0)
        assert p.fuel_state == pytest.approx(expected_state, rel=1e-6)

    def test_fuel_cannot_go_below_zero(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=500.0,
                          fuel_burn_rate_per_tick=20_000.0, fuel_capacity_lbs=100.0,
                          cruise_speed_knots=500.0, fuel_state=0.001)
        fs.resolve_tick({"p1": p}, tick=0)
        assert p.fuel_state >= 0.0


# ── Threshold alert tests ─────────────────────────────────────────────────────

class TestFuelAlerts:
    def test_low_fuel_alert_fires_once(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        # Start just above LOW threshold
        fuel_state = LOW_FUEL_THRESHOLD + 0.001
        p = make_platform(pid="p1", game_id=game_id, speed_knots=500.0,
                          fuel_burn_rate_per_tick=500.0, fuel_capacity_lbs=1000.0,
                          cruise_speed_knots=500.0, fuel_state=fuel_state)

        # Burn until LOW is crossed
        total_low_events = 0
        for tick in range(20):
            r = fs.resolve_tick({"p1": p}, tick=tick)
            for e in r.events:
                if e.type == SimEventType.FUEL_LOW:
                    total_low_events += 1
            if p.fuel_state < BINGO_FUEL_THRESHOLD:
                break

        assert total_low_events == 1, f"Expected exactly 1 FUEL_LOW event, got {total_low_events}"

    def test_bingo_fires_once_and_rtb_order_generated(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        # Start just above BINGO threshold
        fuel_state = BINGO_FUEL_THRESHOLD + 0.001
        p = make_platform(pid="p1", game_id=game_id, speed_knots=500.0,
                          fuel_burn_rate_per_tick=100.0, fuel_capacity_lbs=500.0,
                          cruise_speed_knots=500.0, fuel_state=fuel_state)

        total_bingo = 0
        total_rtb_orders = 0
        for tick in range(20):
            r = fs.resolve_tick({"p1": p}, tick=tick)
            for e in r.events:
                if e.type == SimEventType.FUEL_BINGO:
                    total_bingo += 1
            total_rtb_orders += len(r.rtb_orders)
            if p.fuel_state <= EXHAUSTED_THRESHOLD:
                break

        assert total_bingo == 1, f"Expected exactly 1 FUEL_BINGO event, got {total_bingo}"
        assert total_rtb_orders == 1, "Expected exactly 1 RTB order generated"

    def test_bingo_rtb_order_has_correct_fields(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        fuel_state = BINGO_FUEL_THRESHOLD + 0.001
        p = make_platform(pid="p1", game_id=game_id, speed_knots=500.0,
                          fuel_burn_rate_per_tick=100.0, fuel_capacity_lbs=500.0,
                          cruise_speed_knots=500.0, fuel_state=fuel_state,
                          faction="US")

        for tick in range(10):
            r = fs.resolve_tick({"p1": p}, tick=tick)
            if r.rtb_orders:
                o = r.rtb_orders[0]
                assert o.game_id == game_id
                assert o.platform_id == "p1"
                assert o.order_type.value == "RTB"
                assert len(o.waypoints) == 1
                return

        pytest.fail("No RTB order generated before EXHAUSTED")

    def test_exhausted_airborne_platform_destroyed(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=500.0,
                          fuel_burn_rate_per_tick=50_000.0, fuel_capacity_lbs=100.0,
                          cruise_speed_knots=500.0, fuel_state=0.004,
                          status="IN_TRANSIT", type_key="F35C")

        r = fs.resolve_tick({"p1": p}, tick=0)
        exhaust_events = [e for e in r.events if e.type == SimEventType.FUEL_EXHAUSTED]
        assert len(exhaust_events) == 1
        assert p.status == "DESTROYED"
        assert p.speed_knots == 0.0

    def test_exhausted_surface_platform_not_destroyed(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=30.0,
                          fuel_burn_rate_per_tick=50_000.0, fuel_capacity_lbs=100.0,
                          cruise_speed_knots=30.0, fuel_state=0.004,
                          status="ACTIVE", type_key="SHIP")

        r = fs.resolve_tick({"p1": p}, tick=0)
        exhaust_events = [e for e in r.events if e.type == SimEventType.FUEL_EXHAUSTED]
        assert len(exhaust_events) == 1
        assert p.status != "DESTROYED"


# ── Exclusion tests ───────────────────────────────────────────────────────────

class TestExclusions:
    def test_nuclear_platform_no_burn(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=30.0,
                          fuel_state=0.8, is_nuclear=True)
        result = fs.resolve_tick({"p1": p}, tick=0)
        assert p.fuel_state == 0.8  # unchanged
        assert result.platforms_burned == 0

    def test_destroyed_platform_skipped(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=30.0,
                          fuel_state=0.8, status="DESTROYED")
        result = fs.resolve_tick({"p1": p}, tick=0)
        assert p.fuel_state == 0.8
        assert result.platforms_burned == 0

    def test_zero_capacity_skipped(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        p = make_platform(pid="p1", game_id=game_id, speed_knots=30.0,
                          fuel_capacity_lbs=0.0, fuel_state=0.0)
        result = fs.resolve_tick({"p1": p}, tick=0)
        assert result.platforms_burned == 0


# ── Bulk tests ────────────────────────────────────────────────────────────────

class TestBulkFuel:
    def test_100_platforms_all_burn(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        platforms = make_platforms_grid(100, game_id=game_id,
                                        speed_knots=480.0, fuel_state=1.0)
        for p in platforms.values():
            p.fuel_burn_rate_per_tick = 500.0
            p.fuel_capacity_lbs = 18_500.0
            p.cruise_speed_knots = 480.0

        result = fs.resolve_tick(platforms, tick=0)
        assert result.platforms_burned == 100
        # Every platform should have decreased fuel
        assert all(p.fuel_state < 1.0 for p in platforms.values())

    def test_delta_emitted_per_burning_platform(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        platforms = make_platforms_grid(50, game_id=game_id,
                                        speed_knots=480.0, fuel_state=1.0)
        for p in platforms.values():
            p.fuel_burn_rate_per_tick = 500.0
            p.fuel_capacity_lbs = 18_500.0
            p.cruise_speed_knots = 480.0

        result = fs.resolve_tick(platforms, tick=0)
        assert len(result.deltas) == 50
        delta_ids = {d.id for d in result.deltas}
        assert delta_ids == set(platforms.keys())


# ── Bingo suppression / reset tests ──────────────────────────────────────────

class TestBingoSuppression:
    def test_bingo_not_re_fired_across_ticks(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        # Below BINGO already — should fire once then suppress
        p = make_platform(pid="p1", game_id=game_id, speed_knots=100.0,
                          fuel_burn_rate_per_tick=1.0, fuel_capacity_lbs=1000.0,
                          cruise_speed_knots=100.0, fuel_state=0.09)

        bingo_count = 0
        for tick in range(10):
            r = fs.resolve_tick({"p1": p}, tick=tick)
            bingo_count += sum(1 for e in r.events if e.type == SimEventType.FUEL_BINGO)
            if p.fuel_state <= EXHAUSTED_THRESHOLD:
                break

        assert bingo_count <= 1, f"BINGO should only fire once, fired {bingo_count} times"

    def test_reset_bingo_flags_clears_suppression(self):
        game_id = "g1"
        fs = FuelSubsystem(game_id)
        # Put platform just below BINGO so first tick fires it immediately
        p = make_platform(pid="p1", game_id=game_id, speed_knots=100.0,
                          fuel_burn_rate_per_tick=500.0, fuel_capacity_lbs=1000.0,
                          cruise_speed_knots=100.0, fuel_state=0.105)

        # First pass: fuel drops from 0.105 to 0.055 (burn = 500/1000 = 0.5 per tick)
        # Crosses BINGO (0.10) → fires
        fs.resolve_tick({"p1": p}, tick=0)
        p.fuel_state = 1.0
        fs.reset_bingo_flags(["p1"])

        # Run down again from just above BINGO
        p.fuel_state = 0.105
        bingo_count = 0
        for tick in range(10):
            r = fs.resolve_tick({"p1": p}, tick=tick + 1)
            bingo_count += sum(1 for e in r.events if e.type == SimEventType.FUEL_BINGO)
            if p.fuel_state <= EXHAUSTED_THRESHOLD:
                break

        assert bingo_count == 1, "BINGO should re-fire after flags reset"
