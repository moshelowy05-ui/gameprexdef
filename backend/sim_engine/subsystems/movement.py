"""
Movement subsystem — vectorized great-circle position updates.

Design for 500+ entities per tick:
  - All moving platforms processed in a single NumPy pass (O(N) vectorized)
  - Only platforms that reach a waypoint this tick require individual Python loops
    (typically a small subset → fast fallback)
  - No DB reads during computation (StateManager pre-loaded everything)

Great-circle math:
  Haversine formula for distance.
  Direct formula (spherical trigonometry) for new position given bearing + distance.
  Earth radius: 3440.065 NM (nautical miles).

Coordinate convention: [longitude, latitude] in decimal degrees throughout.

Order of execution inside each tick (enforced by TickEngine):
  1. Apply incoming MOVE_TO / RTB / HOLD / SET_SPEED orders → update MovementState
  2. Run resolve_tick() on all platforms
  3. Return (updated platforms, updated movement states, events emitted)
"""
from __future__ import annotations

import logging
import math
from dataclasses import replace
from typing import NamedTuple

import numpy as np

from sim_engine.models import (
    MovementState,
    OrderType,
    PlatformDelta,
    PlatformHotState,
    PlatformOrder,
    SimEvent,
    SimEventType,
)

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_EARTH_RADIUS_NM: float = 3440.065   # nautical miles
_NM_TO_KM: float = 1.852
_DEG_TO_RAD: float = math.pi / 180.0
_RAD_TO_DEG: float = 180.0 / math.pi

# Platform is considered "at waypoint" when closer than this (nm)
_WAYPOINT_ARRIVAL_RADIUS_NM: float = 0.5

# Stationary platforms with no movement plan skip movement math
_MIN_SPEED_KNOTS: float = 0.1


# ── Pure math functions (used by tests independently) ────────────────────────

def haversine_nm(
    lon1: float | np.ndarray,
    lat1: float | np.ndarray,
    lon2: float | np.ndarray,
    lat2: float | np.ndarray,
) -> float | np.ndarray:
    """
    Haversine great-circle distance in nautical miles.
    Accepts both scalar floats and NumPy arrays (vectorized).
    Time complexity: O(1) scalar, O(N) array.
    """
    lon1r = lon1 * _DEG_TO_RAD
    lat1r = lat1 * _DEG_TO_RAD
    lon2r = lon2 * _DEG_TO_RAD
    lat2r = lat2 * _DEG_TO_RAD

    dlat = lat2r - lat1r
    dlon = lon2r - lon1r

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return _EARTH_RADIUS_NM * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def bearing_deg(
    lon1: float | np.ndarray,
    lat1: float | np.ndarray,
    lon2: float | np.ndarray,
    lat2: float | np.ndarray,
) -> float | np.ndarray:
    """
    Initial bearing (forward azimuth) from point 1 to point 2, in degrees [0, 360).
    Vectorized.
    """
    lon1r = lon1 * _DEG_TO_RAD
    lat1r = lat1 * _DEG_TO_RAD
    lon2r = lon2 * _DEG_TO_RAD
    lat2r = lat2 * _DEG_TO_RAD

    dlon = lon2r - lon1r
    x = np.sin(dlon) * np.cos(lat2r)
    y = np.cos(lat1r) * np.sin(lat2r) - np.sin(lat1r) * np.cos(lat2r) * np.cos(dlon)
    brg = np.degrees(np.arctan2(x, y))
    return (brg + 360.0) % 360.0


def destination_point(
    lon: float | np.ndarray,
    lat: float | np.ndarray,
    brg_deg: float | np.ndarray,
    dist_nm: float | np.ndarray,
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """
    New (lon, lat) after travelling dist_nm on initial bearing brg_deg from (lon, lat).
    Vectorized.
    """
    ang_dist = dist_nm / _EARTH_RADIUS_NM
    brg_r  = brg_deg * _DEG_TO_RAD
    lat1r  = lat * _DEG_TO_RAD
    lon1r  = lon * _DEG_TO_RAD

    new_lat_r = np.arcsin(
        np.sin(lat1r) * np.cos(ang_dist)
        + np.cos(lat1r) * np.sin(ang_dist) * np.cos(brg_r)
    )
    new_lon_r = lon1r + np.arctan2(
        np.sin(brg_r) * np.sin(ang_dist) * np.cos(lat1r),
        np.cos(ang_dist) - np.sin(lat1r) * np.sin(new_lat_r),
    )
    # Normalise longitude to [-180, 180]
    new_lon_deg = (np.degrees(new_lon_r) + 540.0) % 360.0 - 180.0
    return new_lon_deg, np.degrees(new_lat_r)


# ── Result type ───────────────────────────────────────────────────────────────

class MovementTickResult(NamedTuple):
    moved_count: int
    deltas: list[PlatformDelta]
    events: list[SimEvent]
    dirty_movement_states: dict[str, MovementState]   # states that changed this tick


# ── Subsystem ────────────────────────────────────────────────────────────────

class MovementSubsystem:
    """
    Resolves all platform movements for one tick.

    Call order (enforced by TickEngine):
      1. apply_orders(platforms, orders, movement_states, tick)
      2. resolve_tick(platforms, movement_states, tick)
    """

    def apply_orders(
        self,
        platforms: dict[str, PlatformHotState],
        orders: list[PlatformOrder],
        movement_states: dict[str, MovementState | None],
        tick: int,
    ) -> list[SimEvent]:
        """
        Apply MOVE_TO / RTB / HOLD / SET_SPEED / PATROL orders to movement states.
        Modifies movement_states in place.  Returns events generated.

        Called once at the start of the tick, before resolve_tick.
        Time complexity: O(K) where K = number of orders (always << N).
        """
        events: list[SimEvent] = []

        for order in orders:
            pid = order.platform_id
            platform = platforms.get(pid)
            if not platform:
                continue

            if order.order_type == OrderType.MOVE_TO:
                movement_states[pid] = MovementState(
                    waypoints=[[wp.lon, wp.lat] for wp in order.waypoints],
                    current_wp_index=0,
                    hold_ticks_remaining=0,
                    patrol_loop=False,
                )
                # Set speed if specified
                if order.target_speed_knots:
                    platform.speed_knots = order.target_speed_knots
                    platform.is_dirty = True
                if platform.status in ("ACTIVE", "DOCKED"):
                    platform.status = "IN_TRANSIT"
                    platform.is_dirty = True

            elif order.order_type == OrderType.PATROL:
                movement_states[pid] = MovementState(
                    waypoints=[[wp.lon, wp.lat] for wp in order.waypoints],
                    current_wp_index=0,
                    hold_ticks_remaining=0,
                    patrol_loop=True,
                )
                if platform.status in ("ACTIVE", "DOCKED"):
                    platform.status = "IN_TRANSIT"
                    platform.is_dirty = True

            elif order.order_type == OrderType.RTB:
                rtb_pos = None
                if order.waypoints:
                    wp0 = order.waypoints[0]
                    rtb_pos = [wp0.lon, wp0.lat]
                movement_states[pid] = MovementState(
                    waypoints=rtb_pos and [[rtb_pos[0], rtb_pos[1]]] or [],
                    current_wp_index=0,
                    hold_ticks_remaining=0,
                    patrol_loop=False,
                    rtb_position=rtb_pos,
                )
                if platform.status not in ("DESTROYED", "UNDER_MAINTENANCE"):
                    platform.status = "IN_TRANSIT"
                    platform.is_dirty = True

            elif order.order_type == OrderType.HOLD:
                ms = movement_states.get(pid)
                if ms:
                    ms.hold_ticks_remaining = max(ms.hold_ticks_remaining, 1)
                platform.speed_knots = 0.0
                platform.is_dirty = True

            elif order.order_type == OrderType.SET_SPEED:
                if order.target_speed_knots is not None:
                    platform.speed_knots = order.target_speed_knots
                    platform.is_dirty = True

            elif order.order_type == OrderType.ABORT:
                movement_states[pid] = None  # type: ignore[assignment]
                platform.speed_knots = 0.0
                platform.status = "ACTIVE"
                platform.is_dirty = True

        return events

    def resolve_tick(
        self,
        platforms: dict[str, PlatformHotState],
        movement_states: dict[str, MovementState | None],
        tick: int,
    ) -> MovementTickResult:
        """
        Main movement resolution for a single tick.

        Algorithm:
          Phase 1 — Build arrays for all MOVING platforms (vectorized)
          Phase 2 — Compute new positions (NumPy, one pass)
          Phase 3 — Handle waypoint arrivals (per-platform, small set)
          Phase 4 — Write results back to PlatformHotState

        Time complexity:
          - Phase 1: O(N) list comp
          - Phase 2: O(N) vectorized
          - Phase 3: O(A) where A = arrivals (small)
          - Phase 4: O(N) write-back
          Total: O(N) with low constant factor from NumPy
        """
        deltas: list[PlatformDelta] = []
        events: list[SimEvent] = []
        dirty_ms: dict[str, MovementState] = {}

        # ── Phase 1: Gather moving platforms ─────────────────────────────────
        # A platform is "moving" if:
        #   - It has a movement state with remaining waypoints
        #   - It is not on HOLD
        #   - It has speed > threshold (or can use cruise speed)
        #   - It is not DESTROYED / UNDER_MAINTENANCE

        moving_ids: list[str] = []
        moving_platforms: list[PlatformHotState] = []
        moving_states: list[MovementState] = []

        for pid, ms in movement_states.items():
            platform = platforms.get(pid)
            if platform is None or ms is None:
                continue
            if platform.status in ("DESTROYED", "UNDER_MAINTENANCE", "RETIRED"):
                continue
            if ms.hold_ticks_remaining > 0:
                ms.hold_ticks_remaining -= 1
                dirty_ms[pid] = ms
                continue
            if not ms.waypoints or ms.current_wp_index >= len(ms.waypoints):
                continue

            moving_ids.append(pid)
            moving_platforms.append(platform)
            moving_states.append(ms)

        if not moving_ids:
            return MovementTickResult(0, [], [], {})

        n = len(moving_ids)

        # ── Phase 2: Vectorized position update ───────────────────────────────
        # Arrays: all in float64 for numerical stability
        cur_lon = np.array([p.pos_lon for p in moving_platforms], dtype=np.float64)
        cur_lat = np.array([p.pos_lat for p in moving_platforms], dtype=np.float64)

        # Target: current waypoint for each platform
        target_lon = np.array(
            [ms.waypoints[ms.current_wp_index][0] for ms in moving_states], dtype=np.float64
        )
        target_lat = np.array(
            [ms.waypoints[ms.current_wp_index][1] for ms in moving_states], dtype=np.float64
        )

        # Speed: use platform speed if set, else cruise speed from PlatformType
        speeds = np.array(
            [
                p.speed_knots if p.speed_knots > _MIN_SPEED_KNOTS else p.cruise_speed_knots
                for p in moving_platforms
            ],
            dtype=np.float64,
        )

        # Distance this tick: speed (knots) × 1 tick-hour = speed nautical miles
        dist_this_tick = speeds  # 1 tick = 1 game hour → nm = knots × 1 hour

        # Great-circle distance and bearing to next waypoint
        dist_to_wp = haversine_nm(cur_lon, cur_lat, target_lon, target_lat)
        brg = bearing_deg(cur_lon, cur_lat, target_lon, target_lat)

        # Mask: platforms that WILL reach their current waypoint this tick
        reaches_wp_mask: np.ndarray = dist_this_tick >= dist_to_wp

        # For platforms NOT reaching waypoint: compute new position along great circle
        no_reach_mask = ~reaches_wp_mask

        new_lon = cur_lon.copy()
        new_lat = cur_lat.copy()
        new_heading = brg.copy()

        if no_reach_mask.any():
            nl, nlt = destination_point(
                cur_lon[no_reach_mask], cur_lat[no_reach_mask],
                brg[no_reach_mask], dist_this_tick[no_reach_mask],
            )
            new_lon[no_reach_mask] = nl
            new_lat[no_reach_mask] = nlt

        # Platforms reaching waypoint: snap to waypoint position for now,
        # handle multi-waypoint chain in Phase 3
        if reaches_wp_mask.any():
            new_lon[reaches_wp_mask] = target_lon[reaches_wp_mask]
            new_lat[reaches_wp_mask] = target_lat[reaches_wp_mask]

        # ── Phase 3: Waypoint arrival handling ───────────────────────────────
        # Process only platforms that reached their waypoint (small set)
        arrival_indices = np.where(reaches_wp_mask)[0]

        for idx in arrival_indices:
            pid = moving_ids[idx]
            ms = moving_states[idx]
            platform = moving_platforms[idx]

            # Emit waypoint-reached event
            events.append(SimEvent(
                type=SimEventType.WAYPOINT_REACHED,
                tick=tick,
                platform_id=pid,
                game_id=platform.game_id,
                data={
                    "waypoint_index": ms.current_wp_index,
                    "position": [float(target_lon[idx]), float(target_lat[idx])],
                },
                narrative=(
                    f"{platform.type_key} reached waypoint "
                    f"{ms.current_wp_index + 1}/{len(ms.waypoints)}"
                ),
            ))

            next_wp_index = ms.current_wp_index + 1

            if next_wp_index < len(ms.waypoints):
                # Continue to next waypoint — compute remaining distance and move
                remaining_dist = dist_this_tick[idx] - dist_to_wp[idx]
                if remaining_dist > _WAYPOINT_ARRIVAL_RADIUS_NM:
                    nx_lon = ms.waypoints[next_wp_index][0]
                    nx_lat = ms.waypoints[next_wp_index][1]
                    next_brg = bearing_deg(
                        float(target_lon[idx]), float(target_lat[idx]),
                        nx_lon, nx_lat,
                    )
                    dist_to_next = haversine_nm(
                        float(target_lon[idx]), float(target_lat[idx]),
                        nx_lon, nx_lat,
                    )
                    move_dist = min(remaining_dist, float(dist_to_next))
                    nl, nlt = destination_point(
                        float(target_lon[idx]), float(target_lat[idx]),
                        float(next_brg), move_dist,
                    )
                    new_lon[idx] = nl
                    new_lat[idx] = nlt
                    new_heading[idx] = next_brg

                ms.current_wp_index = next_wp_index
                dirty_ms[pid] = ms

            elif ms.patrol_loop and len(ms.waypoints) > 1:
                # Loop back to first waypoint
                ms.current_wp_index = 0
                dirty_ms[pid] = ms
                events.append(SimEvent(
                    type=SimEventType.WAYPOINT_REACHED,
                    tick=tick,
                    platform_id=pid,
                    game_id=platform.game_id,
                    data={"patrol_loop": True},
                    narrative=f"{platform.type_key} completed patrol loop, restarting",
                ))

            else:
                # Final waypoint reached — platform arrives
                ms.waypoints = []
                ms.current_wp_index = 0
                dirty_ms[pid] = ms

                is_rtb = ms.rtb_position is not None
                new_status = "DOCKED" if is_rtb else "ACTIVE"
                new_speed = 0.0

                platform.status = new_status
                platform.speed_knots = new_speed
                platform.is_dirty = True

                events.append(SimEvent(
                    type=SimEventType.MISSION_COMPLETE if not is_rtb
                         else SimEventType.RTB_TRIGGERED,
                    tick=tick,
                    platform_id=pid,
                    game_id=platform.game_id,
                    data={"final_status": new_status},
                    narrative=(
                        f"{platform.type_key} completed route and is now {new_status}"
                        if not is_rtb else
                        f"{platform.type_key} returned to base"
                    ),
                ))

        # ── Phase 4: Write results back ───────────────────────────────────────
        moved_count = 0
        for idx, pid in enumerate(moving_ids):
            platform = moving_platforms[idx]
            old_lon = platform.pos_lon
            old_lat = platform.pos_lat

            nl = float(new_lon[idx])
            nlt = float(new_lat[idx])
            new_hdg = float(new_heading[idx])
            new_spd = float(speeds[idx])

            # Only mark dirty / emit delta if position actually changed
            pos_changed = (
                abs(nl - old_lon) > 1e-7
                or abs(nlt - old_lat) > 1e-7
            )
            if not pos_changed:
                continue

            platform.pos_lon = nl
            platform.pos_lat = nlt
            platform.heading = new_hdg
            if platform.speed_knots < _MIN_SPEED_KNOTS:
                platform.speed_knots = new_spd
            platform.is_dirty = True
            moved_count += 1

            deltas.append(PlatformDelta(
                id=pid,
                position=[nl, nlt],
                heading=new_hdg,
                speed=platform.speed_knots,
            ))

        return MovementTickResult(moved_count, deltas, events, dirty_ms)
