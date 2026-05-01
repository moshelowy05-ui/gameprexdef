"""
Shared test fixtures for sim_engine unit tests.

All tests run without a live database or Redis — subsystems are pure functions
or accept in-memory state.  No I/O mocking needed for unit-level tests.
"""
from __future__ import annotations

# Set env vars before any shared.config import resolves
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/testdb")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

import uuid
from dataclasses import replace

import pytest

from sim_engine.models import (
    MovementState,
    OrderPriority,
    OrderType,
    OrderWaypoint,
    PlatformHotState,
    PlatformOrder,
)


# ── Platform factory ──────────────────────────────────────────────────────────

def make_platform(
    game_id: str = "test-game",
    pid: str | None = None,
    lon: float = 121.5,
    lat: float = 24.0,
    speed_knots: float = 0.0,
    heading: float = 0.0,
    status: str = "ACTIVE",
    fuel_state: float = 1.0,
    faction: str = "US",
    type_key: str = "F35C",
    fuel_burn_rate_per_tick: float = 500.0,   # lbs/tick
    fuel_capacity_lbs: float = 18_500.0,
    cruise_speed_knots: float = 480.0,
    max_range_nm: float = 1200.0,
    is_nuclear: bool = False,
) -> PlatformHotState:
    return PlatformHotState(
        id=pid or str(uuid.uuid4()),
        game_id=game_id,
        type_key=type_key,
        faction=faction,
        status=status,
        pos_lon=lon,
        pos_lat=lat,
        heading=heading,
        speed_knots=speed_knots,
        fuel_state=fuel_state,
        health=1.0,
        fuel_burn_rate_per_tick=fuel_burn_rate_per_tick,
        fuel_capacity_lbs=fuel_capacity_lbs,
        cruise_speed_knots=cruise_speed_knots,
        max_range_nm=max_range_nm,
        is_nuclear=is_nuclear,
    )


def make_move_order(
    game_id: str,
    platform_id: str,
    waypoints: list[list[float]],
    speed_knots: float = 480.0,
    priority: OrderPriority = OrderPriority.ROUTINE,
    tick: int = 0,
) -> PlatformOrder:
    return PlatformOrder(
        id=str(uuid.uuid4()),
        game_id=game_id,
        platform_id=platform_id,
        order_type=OrderType.MOVE_TO,
        priority=priority,
        submission_tick=tick,
        waypoints=[
            OrderWaypoint(lon=wp[0], lat=wp[1], speed_override_knots=speed_knots)
            for wp in waypoints
        ],
        target_speed_knots=speed_knots,
    )


def make_platforms_grid(
    n: int,
    game_id: str = "test-game",
    base_lon: float = 120.0,
    base_lat: float = 20.0,
    step: float = 0.1,
    speed_knots: float = 0.0,
    fuel_state: float = 1.0,
) -> dict[str, PlatformHotState]:
    """Create N platforms on a grid for bulk tests."""
    platforms: dict[str, PlatformHotState] = {}
    for i in range(n):
        pid = f"platform-{i:04d}"
        lon = base_lon + (i % 10) * step
        lat = base_lat + (i // 10) * step
        p = make_platform(
            game_id=game_id,
            pid=pid,
            lon=lon,
            lat=lat,
            speed_knots=speed_knots,
            fuel_state=fuel_state,
        )
        platforms[pid] = p
    return platforms
