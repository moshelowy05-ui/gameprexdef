"""
AdversaryAI — rule-based PLAN tactical behavior.

Called once per tick BEFORE order resolution. Issues movement orders for
PLAN (ADVERSARY_A) platforms that are idle or need re-direction.

Rules:
  PLAN surface ships: every AI_REPLAN_INTERVAL ticks, move toward Taiwan Strait
    Primary objective: [120.5, 24.0] (Taiwan Strait center)
    Secondary: patrol box if already in vicinity
  PLAN aircraft (J-20, J-16): if US aircraft within 400 NM → intercept
    else → patrol route near coast
  PLAN bombers (H-6K): every 20 ticks, fly toward nearest US carrier if known
    (use movement states to check if already in transit)
  PLAN submarines: patrol box [118-125°E, 20-28°N] with waypoints
  PLAN missile batteries (DF, HHQ): fixed — no movement orders

Only issue orders for platforms that have no active movement state or whose
current movement state has no more waypoints.
"""
from __future__ import annotations

import logging
import random
import uuid

from sim_engine.models import (
    MovementState,
    OrderPriority,
    OrderType,
    OrderWaypoint,
    PlatformHotState,
    PlatformOrder,
)
from sim_engine.subsystems.combat import _category

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

AI_REPLAN_INTERVAL = 5   # re-evaluate every 5 ticks

# Taiwan theater patrol waypoints for PLAN surface ships
PLAN_SURFACE_OBJECTIVES: list[list[float]] = [
    [120.5, 25.5],   # Northern Taiwan Strait
    [121.0, 23.5],   # Southern Taiwan Strait
    [122.0, 24.0],   # East of Taiwan
]

# Patrol box for PLAN submarines
PLAN_SUB_PATROL: list[list[float]] = [
    [122.0, 26.0],
    [124.0, 24.0],
    [123.0, 21.0],
    [121.0, 22.0],
]

# PLAN aircraft patrol near coast
PLAN_AIR_PATROL: list[list[float]] = [
    [119.5, 26.0],
    [118.5, 24.5],
    [119.0, 22.0],
    [120.5, 23.0],
]

# UAV coastal patrol zone (random points within this bounding box)
_UAV_PATROL_LON = (118.5, 121.5)
_UAV_PATROL_LAT = (22.0, 26.5)

# Intercept range threshold for PLAN fighters (NM)
_INTERCEPT_RANGE_NM = 400.0


def _haversine_nm(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Inline haversine for use without importing movement (avoids circular deps)."""
    import math
    R = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class AdversaryAI:
    """
    Rule-based AI that issues movement orders for PLAN/ADVERSARY_A platforms
    each tick cycle. Orders are injected into the OrderQueue before resolution.
    """

    def __init__(self, game_id: str) -> None:
        self._game_id = game_id
        self._waypoint_index: dict[str, int] = {}   # platform_id → next waypoint index

    def plan_tick(
        self,
        platforms: dict[str, PlatformHotState],
        movement_states: dict[str, MovementState | None],
        tick: int,
    ) -> list[PlatformOrder]:
        """
        Generate movement orders for adversary platforms that are idle.
        Returns an empty list on ticks where AI does not replan.
        """
        orders: list[PlatformOrder] = []

        if tick % AI_REPLAN_INTERVAL != 0:
            return orders

        adversary_platforms = {
            pid: p for pid, p in platforms.items()
            if p.faction in ("ADVERSARY_A", "PLAN")
            and p.status not in ("DESTROYED", "RETIRED", "IN_PRODUCTION")
        }

        for pid, platform in adversary_platforms.items():
            ms = movement_states.get(pid)
            has_active_movement = (
                ms is not None
                and ms.waypoints
                and ms.current_wp_index < len(ms.waypoints)
            )

            if has_active_movement:
                continue   # Platform is already following orders

            order = self._plan_for_platform(pid, platform, platforms, tick)
            if order:
                orders.append(order)
                log.debug(
                    "AI tick=%d | %s (%s) → %s order issued",
                    tick, platform.type_key, platform.faction, order.order_type,
                )

        return orders

    # ── Per-category planners ─────────────────────────────────────────────────

    def _plan_for_platform(
        self,
        pid: str,
        platform: PlatformHotState,
        all_platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> PlatformOrder | None:
        cat = _category(platform.type_key)

        if cat in ("FACILITY", "UNKNOWN"):
            return None   # Fixed installations — no movement

        if cat == "SHIP":
            return self._plan_surface(pid, platform, tick)
        elif cat == "SUBMARINE":
            return self._plan_submarine(pid, platform, tick)
        elif cat == "AIRCRAFT":
            return self._plan_aircraft(pid, platform, all_platforms, tick)
        elif cat == "UAV":
            return self._plan_uav(pid, platform, tick)

        return None

    def _plan_surface(
        self, pid: str, platform: PlatformHotState, tick: int
    ) -> PlatformOrder:
        """PLAN surface ships cycle through Taiwan Strait objectives."""
        idx = self._waypoint_index.get(pid, 0)
        target = PLAN_SURFACE_OBJECTIVES[idx % len(PLAN_SURFACE_OBJECTIVES)]
        self._waypoint_index[pid] = (idx + 1) % len(PLAN_SURFACE_OBJECTIVES)

        return self._make_move_order(
            pid,
            waypoints=[target],
            speed_knots=platform.cruise_speed_knots,
            tick=tick,
        )

    def _plan_submarine(
        self, pid: str, platform: PlatformHotState, tick: int
    ) -> PlatformOrder:
        """PLAN submarines patrol the Taiwan Strait box on a looping route."""
        idx = self._waypoint_index.get(pid, 0)
        # Issue next single waypoint from the patrol box
        target = PLAN_SUB_PATROL[idx % len(PLAN_SUB_PATROL)]
        self._waypoint_index[pid] = (idx + 1) % len(PLAN_SUB_PATROL)

        # Submarines run slow for acoustic stealth
        speed = min(10.0, platform.cruise_speed_knots)

        return PlatformOrder(
            id=str(uuid.uuid4()),
            game_id=self._game_id,
            platform_id=pid,
            order_type=OrderType.PATROL,
            priority=OrderPriority.ROUTINE,
            submission_tick=tick,
            waypoints=[OrderWaypoint(lon=target[0], lat=target[1], speed_override_knots=speed)],
            target_speed_knots=speed,
        )

    def _plan_aircraft(
        self,
        pid: str,
        platform: PlatformHotState,
        all_platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> PlatformOrder:
        """
        PLAN fighters intercept nearby US aircraft;
        otherwise patrol coastal route.
        """
        # Find nearest US aircraft
        nearest_us_aircraft: PlatformHotState | None = None
        nearest_dist = float("inf")

        for other_id, other in all_platforms.items():
            if other.faction != "US":
                continue
            if other.status in ("DESTROYED", "RETIRED", "IN_PRODUCTION"):
                continue
            if _category(other.type_key) != "AIRCRAFT":
                continue

            dist = _haversine_nm(
                platform.pos_lon, platform.pos_lat,
                other.pos_lon, other.pos_lat,
            )
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_us_aircraft = other

        if nearest_us_aircraft is not None and nearest_dist <= _INTERCEPT_RANGE_NM:
            # Intercept
            target = [nearest_us_aircraft.pos_lon, nearest_us_aircraft.pos_lat]
            log.debug(
                "AI INTERCEPT: %s heading for US %s at %.0f NM",
                platform.type_key, nearest_us_aircraft.type_key, nearest_dist,
            )
            return self._make_move_order(
                pid,
                waypoints=[target],
                speed_knots=platform.cruise_speed_knots,
                tick=tick,
            )

        # Coastal patrol
        idx = self._waypoint_index.get(pid, 0)
        target = PLAN_AIR_PATROL[idx % len(PLAN_AIR_PATROL)]
        self._waypoint_index[pid] = (idx + 1) % len(PLAN_AIR_PATROL)

        return self._make_move_order(
            pid,
            waypoints=[target],
            speed_knots=platform.cruise_speed_knots,
            tick=tick,
        )

    def _plan_uav(
        self, pid: str, platform: PlatformHotState, tick: int
    ) -> PlatformOrder:
        """UAVs get a random coastal patrol point."""
        lon = random.uniform(*_UAV_PATROL_LON)
        lat = random.uniform(*_UAV_PATROL_LAT)
        return self._make_move_order(
            pid,
            waypoints=[[lon, lat]],
            speed_knots=platform.cruise_speed_knots,
            tick=tick,
        )

    # ── Helper ────────────────────────────────────────────────────────────────

    def _make_move_order(
        self,
        platform_id: str,
        waypoints: list[list[float]],
        speed_knots: float,
        tick: int,
    ) -> PlatformOrder:
        wps = [
            OrderWaypoint(lon=wp[0], lat=wp[1], speed_override_knots=speed_knots)
            for wp in waypoints
        ]
        return PlatformOrder(
            id=str(uuid.uuid4()),
            game_id=self._game_id,
            platform_id=platform_id,
            order_type=OrderType.MOVE_TO,
            priority=OrderPriority.ROUTINE,
            submission_tick=tick,
            waypoints=wps,
            target_speed_knots=speed_knots,
        )
