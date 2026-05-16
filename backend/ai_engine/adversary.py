"""
AdversaryAI — rule-based PLAN tactical behavior (upgraded).

Called once per tick BEFORE order resolution. Issues movement orders for
PLAN (ADVERSARY_A) platforms that are idle or need re-direction.

Threat priority (higher priority overrides lower):
  1. Hunt US carriers (CVN) if within 600 NM — highest value target
  2. Intercept US aircraft within 400 NM (fighters/bombers)
  3. Hunt US surface combatants within 300 NM (ships)
  4. Default patrol patterns

PLAN bombers (H-6K) actively fly toward the nearest US carrier or surface
group when one is detected within strike range.

PLAN submarines close to intercept US carrier groups and set up ambush
positions ahead of the group's projected track.

Missile batteries (DF, HHQ, YJ) do not move — they are fixed installations.
"""
from __future__ import annotations

import logging
import math
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

AI_REPLAN_INTERVAL = 4   # re-evaluate every 4 ticks

# Threat detection ranges
_CARRIER_HUNT_RANGE_NM    = 600.0  # surface ships hunting carriers
_SHIP_HUNT_RANGE_NM       = 350.0  # subs/aircraft hunting any US surface unit
_INTERCEPT_RANGE_NM       = 450.0  # fighters intercepting aircraft
_BOMBER_STRIKE_RANGE_NM   = 1800.0 # H-6K cruise missile launch range

# Tactical patrol waypoints — Taiwan theater
PLAN_SURFACE_OBJECTIVES: list[list[float]] = [
    [120.5, 25.5],   # Northern Taiwan Strait
    [121.5, 24.0],   # Central Taiwan Strait
    [121.0, 23.0],   # Southern Taiwan Strait
    [122.5, 24.5],   # East of Taiwan (ASuW position)
]

PLAN_SUB_PATROL: list[list[float]] = [
    [123.0, 26.5],
    [124.5, 24.5],
    [123.5, 22.0],
    [121.5, 21.5],
    [120.0, 23.0],
]

PLAN_AIR_PATROL: list[list[float]] = [
    [119.5, 26.0],
    [118.5, 24.5],
    [119.0, 22.5],
    [120.5, 23.0],
    [121.0, 25.0],
]

_UAV_PATROL_LON = (118.5, 122.0)
_UAV_PATROL_LAT = (21.5, 26.5)


def _haversine_nm(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _closest_us_target(
    platform: PlatformHotState,
    all_platforms: dict[str, PlatformHotState],
    target_categories: set[str],
    max_range_nm: float,
    exclude_classes: set[str] | None = None,
) -> tuple[PlatformHotState | None, float]:
    """Return (closest US platform matching categories, distance) within max_range_nm."""
    best: PlatformHotState | None = None
    best_dist = float("inf")

    for other in all_platforms.values():
        if other.faction != "US":
            continue
        if other.status in ("DESTROYED", "RETIRED", "IN_PRODUCTION"):
            continue
        if other.pos_lat is None or other.pos_lon is None:
            continue
        cat = _category(other.type_key)
        if cat not in target_categories:
            continue
        if exclude_classes and other.type_key.upper().startswith(tuple(e.upper() for e in exclude_classes)):
            continue

        dist = _haversine_nm(platform.pos_lon, platform.pos_lat, other.pos_lon, other.pos_lat)
        if dist < best_dist and dist <= max_range_nm:
            best = other
            best_dist = dist

    return best, best_dist


class AdversaryAI:
    """Rule-based AI issuing movement orders for PLAN/ADVERSARY_A each tick."""

    def __init__(self, game_id: str) -> None:
        self._game_id = game_id
        self._waypoint_index: dict[str, int] = {}

    def plan_tick(
        self,
        platforms: dict[str, PlatformHotState],
        movement_states: dict[str, MovementState | None],
        tick: int,
    ) -> list[PlatformOrder]:
        orders: list[PlatformOrder] = []

        if tick % AI_REPLAN_INTERVAL != 0:
            return orders

        adversary_platforms = {
            pid: p for pid, p in platforms.items()
            if p.faction in ("ADVERSARY_A", "PLAN")
            and p.status not in ("DESTROYED", "RETIRED", "IN_PRODUCTION")
            and p.pos_lat is not None and p.pos_lon is not None
        }

        for pid, platform in adversary_platforms.items():
            ms = movement_states.get(pid)
            has_active_movement = (
                ms is not None
                and ms.waypoints
                and ms.current_wp_index < len(ms.waypoints)
            )
            if has_active_movement:
                continue

            order = self._plan_for_platform(pid, platform, platforms, tick)
            if order:
                orders.append(order)
                log.debug(
                    "AI tick=%d | %s (%s) → %s",
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

        if cat in ("FACILITY", "UNKNOWN", "MISSILE"):
            return None

        if cat == "SHIP":
            return self._plan_surface(pid, platform, all_platforms, tick)
        elif cat == "SUBMARINE":
            return self._plan_submarine(pid, platform, all_platforms, tick)
        elif cat == "AIRCRAFT":
            return self._plan_aircraft(pid, platform, all_platforms, tick)
        elif cat == "UAV":
            return self._plan_uav(pid, platform, all_platforms, tick)

        return None

    def _plan_surface(
        self,
        pid: str,
        platform: PlatformHotState,
        all_platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> PlatformOrder:
        """PLAN surface combatants hunt US carriers; otherwise advance through Taiwan Strait."""
        # Priority 1: close on US carrier
        carrier, dist = _closest_us_target(
            platform, all_platforms,
            target_categories={"SHIP"},
            max_range_nm=_CARRIER_HUNT_RANGE_NM,
        )
        if carrier is not None:
            # Intercept at a cautious offset (don't sail directly into fire)
            offset_lon = carrier.pos_lon + random.uniform(-0.3, 0.3)
            offset_lat = carrier.pos_lat + random.uniform(-0.3, 0.3)
            log.debug("AI surface %s hunting US ship at %.0f NM", platform.type_key, dist)
            return self._make_move_order(
                pid,
                waypoints=[[offset_lon, offset_lat]],
                speed_knots=platform.cruise_speed_knots,
                tick=tick,
            )

        # Default: advance through Taiwan Strait patrol pattern
        idx = self._waypoint_index.get(pid, 0)
        target = PLAN_SURFACE_OBJECTIVES[idx % len(PLAN_SURFACE_OBJECTIVES)]
        self._waypoint_index[pid] = (idx + 1) % len(PLAN_SURFACE_OBJECTIVES)
        return self._make_move_order(pid, waypoints=[target], speed_knots=platform.cruise_speed_knots, tick=tick)

    def _plan_submarine(
        self,
        pid: str,
        platform: PlatformHotState,
        all_platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> PlatformOrder:
        """PLAN submarines stalk US ships stealthily at slow speed."""
        speed = min(8.0, platform.cruise_speed_knots)  # acoustic stealth

        # Hunt US surface ships
        target_ship, dist = _closest_us_target(
            platform, all_platforms,
            target_categories={"SHIP"},
            max_range_nm=_SHIP_HUNT_RANGE_NM,
        )
        if target_ship is not None:
            # Aim at an intercept point slightly offset for ambush geometry
            intercept_lon = target_ship.pos_lon + random.uniform(-0.5, 0.5)
            intercept_lat = target_ship.pos_lat + random.uniform(-0.5, 0.5)
            log.debug("AI sub %s stalking US ship at %.0f NM", platform.type_key, dist)
            return PlatformOrder(
                id=str(uuid.uuid4()),
                game_id=self._game_id,
                platform_id=pid,
                order_type=OrderType.PATROL,
                priority=OrderPriority.URGENT,
                submission_tick=tick,
                waypoints=[OrderWaypoint(lon=intercept_lon, lat=intercept_lat, speed_override_knots=speed)],
                target_speed_knots=speed,
            )

        # Default patrol
        idx = self._waypoint_index.get(pid, 0)
        target = PLAN_SUB_PATROL[idx % len(PLAN_SUB_PATROL)]
        self._waypoint_index[pid] = (idx + 1) % len(PLAN_SUB_PATROL)
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
        PLAN aircraft:
        - H-6 bombers → strike nearest US carrier/surface group
        - J-20/J-16 fighters → intercept nearest US aircraft
        - Else → coastal patrol
        """
        tk = platform.type_key.upper()
        is_bomber = tk.startswith("H6") or tk.startswith("H-6")

        if is_bomber:
            # Bombers seek out US ships for cruise missile strikes
            target, dist = _closest_us_target(
                platform, all_platforms,
                target_categories={"SHIP"},
                max_range_nm=_BOMBER_STRIKE_RANGE_NM,
            )
            if target is not None:
                # Fly to within 400 NM for cruise missile launch (stand-off)
                bearing_rad = math.atan2(
                    math.radians(target.pos_lon - platform.pos_lon),
                    math.radians(target.pos_lat - platform.pos_lat),
                )
                standoff_nm = 350.0
                standoff_lat = platform.pos_lat + math.cos(bearing_rad) * (standoff_nm / 60.0)
                standoff_lon = platform.pos_lon + math.sin(bearing_rad) * (standoff_nm / 60.0)
                log.debug("AI bomber %s approaching US ship for strike at %.0f NM", platform.type_key, dist)
                return self._make_move_order(
                    pid,
                    waypoints=[[standoff_lon, standoff_lat]],
                    speed_knots=platform.cruise_speed_knots,
                    tick=tick,
                )

        # Fighters/all aircraft: intercept nearest US aircraft
        target_ac, dist_ac = _closest_us_target(
            platform, all_platforms,
            target_categories={"AIRCRAFT", "UAV"},
            max_range_nm=_INTERCEPT_RANGE_NM,
        )
        if target_ac is not None:
            log.debug("AI aircraft %s intercepting US %s at %.0f NM", platform.type_key, target_ac.type_key, dist_ac)
            return self._make_move_order(
                pid,
                waypoints=[[target_ac.pos_lon, target_ac.pos_lat]],
                speed_knots=platform.cruise_speed_knots,
                tick=tick,
            )

        # Intercept nearest US ship as secondary target
        target_ship, dist_ship = _closest_us_target(
            platform, all_platforms,
            target_categories={"SHIP"},
            max_range_nm=_INTERCEPT_RANGE_NM,
        )
        if target_ship is not None:
            return self._make_move_order(
                pid,
                waypoints=[[target_ship.pos_lon, target_ship.pos_lat]],
                speed_knots=platform.cruise_speed_knots,
                tick=tick,
            )

        # Default: coastal patrol
        idx = self._waypoint_index.get(pid, 0)
        target_wp = PLAN_AIR_PATROL[idx % len(PLAN_AIR_PATROL)]
        self._waypoint_index[pid] = (idx + 1) % len(PLAN_AIR_PATROL)
        return self._make_move_order(pid, waypoints=[target_wp], speed_knots=platform.cruise_speed_knots, tick=tick)

    def _plan_uav(
        self,
        pid: str,
        platform: PlatformHotState,
        all_platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> PlatformOrder:
        """UAVs conduct ISR patrols toward US fleet positions."""
        # Try to fly toward nearest US ship for ISR (but stay back)
        target, dist = _closest_us_target(
            platform, all_platforms,
            target_categories={"SHIP", "AIRCRAFT"},
            max_range_nm=250.0,
        )
        if target is not None:
            # Patrol at safe standoff distance
            bearing_rad = math.atan2(
                math.radians(target.pos_lon - platform.pos_lon),
                math.radians(target.pos_lat - platform.pos_lat),
            )
            standoff_nm = 100.0
            patrol_lat = platform.pos_lat + math.cos(bearing_rad) * (standoff_nm / 60.0)
            patrol_lon = platform.pos_lon + math.sin(bearing_rad) * (standoff_nm / 60.0)
            return self._make_move_order(
                pid,
                waypoints=[[patrol_lon, patrol_lat]],
                speed_knots=platform.cruise_speed_knots,
                tick=tick,
            )

        lon = random.uniform(*_UAV_PATROL_LON)
        lat = random.uniform(*_UAV_PATROL_LAT)
        return self._make_move_order(pid, waypoints=[[lon, lat]], speed_knots=platform.cruise_speed_knots, tick=tick)

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
