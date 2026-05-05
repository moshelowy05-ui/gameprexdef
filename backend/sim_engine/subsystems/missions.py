"""
MissionSubsystem — route platforms toward mission objectives each tick.

Handles STRIKE and CAP mission types:
  STRIKE: move assigned task force platforms toward target, emit execution events
          when within firing range with enemy nearby.
  CAP:    cycle assigned fighters through the mission's waypoints.

Completion check: STRIKE missions complete when no living ADVERSARY platforms
remain within 50 NM of the target area.

Combat is NOT resolved here — CombatSubsystem handles that.
MissionSubsystem only routes platforms toward objectives.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sim_engine.models import (
    OrderPriority,
    OrderType,
    OrderWaypoint,
    PlatformHotState,
    PlatformOrder,
    SimEvent,
    SimEventType,
)
from sim_engine.subsystems.movement import haversine_nm

log = logging.getLogger(__name__)

_ADVERSARY_FACTIONS = {"ADVERSARY_A", "ADVERSARY_B", "PLAN"}

# Radius within which a STRIKE mission is considered complete (NM)
_STRIKE_COMPLETE_RADIUS_NM = 50.0
# Radius within which "enemy nearby" triggers execution event (NM)
_ENEMY_NEARBY_RADIUS_NM = 200.0


@dataclass
class MissionTickResult:
    events: list[SimEvent] = field(default_factory=list)
    mission_updates: list[dict] = field(default_factory=list)
    injected_orders: list[PlatformOrder] = field(default_factory=list)


class MissionSubsystem:
    def __init__(self, game_id: str) -> None:
        self._game_id = game_id

    async def resolve_tick(
        self,
        platforms: dict[str, PlatformHotState],
        db_session,
        tick: int,
    ) -> MissionTickResult:
        """
        Evaluate all PLANNED/ACTIVE missions for the current tick.

        Returns MissionTickResult with events, mission status updates, and
        movement orders to inject back into the movement subsystem.
        """
        from sqlalchemy import select
        from shared.db_models import MissionORM, TaskForceORM

        result = MissionTickResult()

        try:
            # Load PLANNED and ACTIVE missions
            missions_result = await db_session.execute(
                select(MissionORM).where(
                    MissionORM.session_id == uuid.UUID(self._game_id),
                    MissionORM.status.in_(["PLANNED", "ACTIVE"]),
                )
            )
            missions = missions_result.scalars().all()

            if not missions:
                return result

            # Build adversary platform lookup for quick range checks
            adversary_platforms = [
                p for p in platforms.values()
                if p.faction in _ADVERSARY_FACTIONS
                and p.status not in ("DESTROYED", "RETIRED")
                and p.health > 0
            ]

            for mission in missions:
                try:
                    await self._process_mission(
                        mission=mission,
                        platforms=platforms,
                        adversary_platforms=adversary_platforms,
                        db_session=db_session,
                        tick=tick,
                        result=result,
                    )
                except Exception as exc:
                    log.error(
                        "Error processing mission %s (game=%s, tick=%d): %s",
                        str(mission.id)[:8], self._game_id, tick, exc,
                    )

            await db_session.commit()

        except Exception as exc:
            log.error(
                "MissionSubsystem.resolve_tick error (game=%s, tick=%d): %s",
                self._game_id, tick, exc,
            )

        return result

    async def _process_mission(
        self,
        mission,
        platforms: dict[str, PlatformHotState],
        adversary_platforms: list[PlatformHotState],
        db_session,
        tick: int,
        result: MissionTickResult,
    ) -> None:
        from sqlalchemy import select
        from shared.db_models import TaskForceORM

        mission_id_str = str(mission.id)

        # ── PLANNED → ACTIVE transition ───────────────────────────────────────
        if mission.status == "PLANNED":
            if tick >= mission.start_tick:
                mission.status = "ACTIVE"
                result.mission_updates.append({
                    "mission_id": mission_id_str,
                    "status": "ACTIVE",
                    "tick": tick,
                    "name": mission.name,
                })
                log.info(
                    "Mission %s (%s) activated at tick %d",
                    mission.name, mission_id_str[:8], tick,
                )
            else:
                return  # Not yet time

        # From here on, mission.status == "ACTIVE"
        mission_type = mission.mission_type.upper()

        # Get the assigned task force's platform IDs
        tf_result = await db_session.execute(
            select(TaskForceORM).where(TaskForceORM.id == mission.assigned_tf_id)
        )
        task_force = tf_result.scalar_one_or_none()
        if task_force is None:
            log.warning(
                "Mission %s references missing TaskForce %s",
                mission_id_str[:8], str(mission.assigned_tf_id)[:8],
            )
            return

        tf_platform_ids: set[str] = {
            str(pid) for pid in (task_force.assigned_unit_ids or [])
        }

        # Find eligible platforms: in TF, faction US, ACTIVE or IN_TRANSIT, health > 0
        eligible_platforms = [
            p for p in platforms.values()
            if p.id in tf_platform_ids
            and p.faction == "US"
            and p.status in ("ACTIVE", "IN_TRANSIT")
            and p.health > 0
        ]

        if mission_type == "STRIKE":
            await self._process_strike_mission(
                mission=mission,
                eligible_platforms=eligible_platforms,
                adversary_platforms=adversary_platforms,
                platforms=platforms,
                tick=tick,
                result=result,
            )
        elif mission_type == "CAP":
            self._process_cap_mission(
                mission=mission,
                eligible_platforms=eligible_platforms,
                tick=tick,
                result=result,
            )
        elif mission_type == "PATROL":
            self._process_patrol_mission(
                mission=mission,
                eligible_platforms=eligible_platforms,
                tick=tick,
                result=result,
            )
        elif mission_type == "RECON":
            self._process_recon_mission(
                mission=mission,
                eligible_platforms=eligible_platforms,
                tick=tick,
                result=result,
            )
        elif mission_type == "ESCORT":
            self._process_escort_mission(
                mission=mission,
                eligible_platforms=eligible_platforms,
                tick=tick,
                result=result,
            )
        elif mission_type == "ASW":
            self._process_asw_mission(
                mission=mission,
                eligible_platforms=eligible_platforms,
                tick=tick,
                result=result,
            )
        elif mission_type == "SEAD":
            await self._process_sead_mission(
                mission=mission,
                eligible_platforms=eligible_platforms,
                adversary_platforms=adversary_platforms,
                platforms=platforms,
                tick=tick,
                result=result,
            )

        # ── Completion check for STRIKE ───────────────────────────────────────
        if mission_type == "STRIKE":
            target_lon, target_lat = self._get_target_position(mission.target)
            if target_lon is not None:
                adversaries_in_area = [
                    p for p in adversary_platforms
                    if haversine_nm(p.pos_lon, p.pos_lat, target_lon, target_lat)
                    <= _STRIKE_COMPLETE_RADIUS_NM
                ]
                if not adversaries_in_area and eligible_platforms:
                    mission.status = "COMPLETE"
                    result.mission_updates.append({
                        "mission_id": mission_id_str,
                        "status": "COMPLETE",
                        "tick": tick,
                        "name": mission.name,
                    })
                    result.events.append(SimEvent(
                        type=SimEventType.MISSION_COMPLETE,
                        tick=tick,
                        game_id=self._game_id,
                        data={
                            "mission_id": mission_id_str,
                            "mission_name": mission.name,
                            "mission_type": mission_type,
                        },
                        narrative=f"Strike mission '{mission.name}' complete — target area clear",
                    ))
                    log.info(
                        "Mission %s (%s) completed at tick %d",
                        mission.name, mission_id_str[:8], tick,
                    )

    async def _process_strike_mission(
        self,
        mission,
        eligible_platforms: list[PlatformHotState],
        adversary_platforms: list[PlatformHotState],
        platforms: dict[str, PlatformHotState],
        tick: int,
        result: MissionTickResult,
    ) -> None:
        target_lon, target_lat = self._get_target_position(mission.target)
        if target_lon is None:
            log.warning(
                "STRIKE mission %s has no valid target position",
                str(mission.id)[:8],
            )
            return

        for platform in eligible_platforms:
            dist_to_target = haversine_nm(
                platform.pos_lon, platform.pos_lat, target_lon, target_lat
            )

            # Only route platforms within max_range_nm * 2
            if dist_to_target > platform.max_range_nm * 2:
                continue

            # Check if already heading toward target vicinity (< 50 NM)
            if dist_to_target < 50.0:
                # Platform is near target — check for nearby enemies and emit event
                nearby_enemies = [
                    p for p in adversary_platforms
                    if haversine_nm(p.pos_lon, p.pos_lat, target_lon, target_lat)
                    <= _ENEMY_NEARBY_RADIUS_NM
                ]
                if nearby_enemies:
                    result.events.append(SimEvent(
                        type=SimEventType.PLATFORM_STATUS_CHANGE,
                        tick=tick,
                        platform_id=platform.id,
                        game_id=self._game_id,
                        data={"mission_executing": True},
                        narrative=(
                            f"{platform.type_key} executing strike mission "
                            f"'{mission.name}' — {len(nearby_enemies)} enemy contact(s) nearby"
                        ),
                    ))
                continue  # Already in position; no new order needed

            # Issue MOVE_TO order toward the target
            order = PlatformOrder(
                id=str(uuid.uuid4()),
                game_id=self._game_id,
                platform_id=platform.id,
                order_type=OrderType.MOVE_TO,
                priority=OrderPriority.MISSION,
                submission_tick=tick,
                waypoints=[
                    OrderWaypoint(
                        lon=target_lon,
                        lat=target_lat,
                        action="STRIKE",
                    )
                ],
                mission_id=str(mission.id),
            )
            result.injected_orders.append(order)

    def _process_cap_mission(
        self,
        mission,
        eligible_platforms: list[PlatformHotState],
        tick: int,
        result: MissionTickResult,
    ) -> None:
        waypoints: list[dict] = mission.waypoints or []
        if not waypoints:
            return

        for platform in eligible_platforms:
            # Find the next waypoint to route toward (cycle through)
            # Use a simple hash of platform_id + tick to spread platforms across waypoints
            wp_index = (hash(platform.id) + tick // max(1, len(waypoints))) % len(waypoints)
            wp = waypoints[wp_index]

            wp_lon = wp.get("lon") or (wp.get("position") or [None, None])[0]
            wp_lat = wp.get("lat") or (wp.get("position") or [None, None])[1]

            if wp_lon is None or wp_lat is None:
                continue

            dist = haversine_nm(platform.pos_lon, platform.pos_lat, wp_lon, wp_lat)
            if dist < 20.0:
                # Already at/near this waypoint; advance to next
                wp_index = (wp_index + 1) % len(waypoints)
                wp = waypoints[wp_index]
                wp_lon = wp.get("lon") or (wp.get("position") or [None, None])[0]
                wp_lat = wp.get("lat") or (wp.get("position") or [None, None])[1]
                if wp_lon is None or wp_lat is None:
                    continue

            order = PlatformOrder(
                id=str(uuid.uuid4()),
                game_id=self._game_id,
                platform_id=platform.id,
                order_type=OrderType.PATROL,
                priority=OrderPriority.MISSION,
                submission_tick=tick,
                waypoints=[
                    OrderWaypoint(
                        lon=float(wp_lon),
                        lat=float(wp_lat),
                        action="TRANSIT",
                    )
                ],
                mission_id=str(mission.id),
            )
            result.injected_orders.append(order)

    def _process_patrol_mission(
        self,
        mission,
        eligible_platforms: list[PlatformHotState],
        tick: int,
        result: MissionTickResult,
    ) -> None:
        """PATROL — identical to CAP: cycle platforms through mission waypoints."""
        self._process_cap_mission(
            mission=mission,
            eligible_platforms=eligible_platforms,
            tick=tick,
            result=result,
        )

    def _process_recon_mission(
        self,
        mission,
        eligible_platforms: list[PlatformHotState],
        tick: int,
        result: MissionTickResult,
    ) -> None:
        """RECON — like PATROL but prefers ISR-capable platforms.
        Every 5 ticks, emit a PLATFORM_STATUS_CHANGE event with recon_report data."""
        # Prefer ISR-capable platforms (type_key contains common ISR designators)
        _ISR_KEYS = ("P8", "E2", "E8", "RQ", "MQ", "U2", "RC", "EP3", "JSTARS", "AWACS")
        isr_platforms = [
            p for p in eligible_platforms
            if any(k in p.type_key.upper() for k in _ISR_KEYS)
        ]
        platforms_to_route = isr_platforms if isr_platforms else eligible_platforms

        # Route platforms through waypoints (same logic as CAP)
        self._process_cap_mission(
            mission=mission,
            eligible_platforms=platforms_to_route,
            tick=tick,
            result=result,
        )

        # Every 5 ticks emit a recon report for each platform on route
        if tick % 5 == 0:
            for platform in platforms_to_route:
                result.events.append(SimEvent(
                    type=SimEventType.PLATFORM_STATUS_CHANGE,
                    tick=tick,
                    platform_id=platform.id,
                    game_id=self._game_id,
                    data={"recon_report": True, "tick": tick},
                    narrative=(
                        f"{platform.type_key} filed recon report on mission "
                        f"'{mission.name}' at tick {tick}"
                    ),
                ))

    def _process_escort_mission(
        self,
        mission,
        eligible_platforms: list[PlatformHotState],
        tick: int,
        result: MissionTickResult,
    ) -> None:
        """ESCORT — keep assigned platforms within 30 NM of the mission's target position."""
        target_lon, target_lat = self._get_target_position(mission.target)
        if target_lon is None:
            log.warning(
                "ESCORT mission %s has no valid target position",
                str(mission.id)[:8],
            )
            return

        for platform in eligible_platforms:
            dist = haversine_nm(platform.pos_lon, platform.pos_lat, target_lon, target_lat)
            if dist <= 30.0:
                continue  # Already within escort range

            order = PlatformOrder(
                id=str(uuid.uuid4()),
                game_id=self._game_id,
                platform_id=platform.id,
                order_type=OrderType.MOVE_TO,
                priority=OrderPriority.MISSION,
                submission_tick=tick,
                waypoints=[
                    OrderWaypoint(
                        lon=target_lon,
                        lat=target_lat,
                        action="TRANSIT",
                    )
                ],
                mission_id=str(mission.id),
            )
            result.injected_orders.append(order)

    def _process_asw_mission(
        self,
        mission,
        eligible_platforms: list[PlatformHotState],
        tick: int,
        result: MissionTickResult,
    ) -> None:
        """ASW — like PATROL but only route ASW-capable platform types."""
        _ASW_PREFIXES = ("SSN_", "SSK_", "P8A", "MH60R")
        asw_platforms = [
            p for p in eligible_platforms
            if any(p.type_key.upper().startswith(prefix) for prefix in _ASW_PREFIXES)
        ]
        if not asw_platforms:
            return

        self._process_cap_mission(
            mission=mission,
            eligible_platforms=asw_platforms,
            tick=tick,
            result=result,
        )

    async def _process_sead_mission(
        self,
        mission,
        eligible_platforms: list[PlatformHotState],
        adversary_platforms: list[PlatformHotState],
        platforms: dict[str, PlatformHotState],
        tick: int,
        result: MissionTickResult,
    ) -> None:
        """SEAD — like STRIKE but targets SAM/radar facilities.
        Identical movement injection pattern to STRIKE."""
        await self._process_strike_mission(
            mission=mission,
            eligible_platforms=eligible_platforms,
            adversary_platforms=adversary_platforms,
            platforms=platforms,
            tick=tick,
            result=result,
        )

    @staticmethod
    def _get_target_position(target: dict) -> tuple[float | None, float | None]:
        """Extract (lon, lat) from a target dict that may use different schemas."""
        if not target:
            return None, None
        # Schema 1: {"lon": ..., "lat": ...}
        if "lon" in target and "lat" in target:
            return float(target["lon"]), float(target["lat"])
        # Schema 2: {"position": [lon, lat]}
        pos = target.get("position")
        if pos and len(pos) >= 2:
            return float(pos[0]), float(pos[1])
        return None, None
