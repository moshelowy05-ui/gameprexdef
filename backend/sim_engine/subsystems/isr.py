"""
ISRSubsystem — Intelligence, Surveillance, Reconnaissance.

Each tick: platforms with ISR capability (recon aircraft, satellites, subs)
scan their current position for enemy platforms within sensor range.
Creates/updates IntelTrackORM entries in the DB for discovered platforms.
"""
from __future__ import annotations
import logging
import math
import uuid
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Platform type keys with ISR capability and their sensor range (NM)
ISR_SENSORS: dict[str, float] = {
    "P8A": 300.0,       # maritime patrol aircraft
    "E2D": 250.0,       # airborne early warning
    "RQ4": 400.0,       # global hawk UAV
    "EP3": 200.0,       # signals intelligence
    "SSN_": 80.0,       # submarine sonar (prefix match)
    "CVN_": 120.0,      # carrier radar (prefix match)
}

# How often ISR actually reports (every N ticks)
ISR_REPORT_INTERVAL = 3

@dataclass
class ISRTickResult:
    tracks_created: int = 0
    tracks_updated: int = 0
    intel_events: list[dict] = field(default_factory=list)

class ISRSubsystem:
    def __init__(self, game_id: str) -> None:
        self._game_id = game_id

    def _get_sensor_range(self, type_key: str) -> float:
        for key, rng in ISR_SENSORS.items():
            if type_key.startswith(key) or type_key == key:
                return rng
        return 0.0

    async def resolve_tick(
        self,
        platforms,  # dict[str, PlatformHotState]
        db_session,
        tick: int,
    ) -> ISRTickResult:
        if tick % ISR_REPORT_INTERVAL != 0:
            return ISRTickResult()

        result = ISRTickResult()
        try:
            from shared.db_models import IntelTrackORM
            from sqlalchemy import select

            # Find ISR platforms
            isr_platforms = [
                p for p in platforms.values()
                if self._get_sensor_range(p.type_key) > 0
                and p.status not in ("DESTROYED", "RETIRED")
                and p.faction == "US"
            ]

            if not isr_platforms:
                return result

            # Identify ADVERSARY platforms to track
            adversary = [
                p for p in platforms.values()
                if p.faction in ("ADVERSARY_A", "PLAN")
                and p.status not in ("DESTROYED", "RETIRED")
            ]

            for isr_p in isr_platforms:
                sensor_range = self._get_sensor_range(isr_p.type_key)
                for target in adversary:
                    # Haversine distance check (inline to avoid import overhead)
                    lat1 = math.radians(isr_p.pos_lat)
                    lat2 = math.radians(target.pos_lat)
                    dlon = math.radians(target.pos_lon - isr_p.pos_lon)
                    dlat = lat2 - lat1
                    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
                    dist_nm = 2 * math.asin(math.sqrt(a)) * 3440.065

                    if dist_nm > sensor_range:
                        continue

                    # Confidence based on range (1.0 at 0nm, 0.5 at sensor_range)
                    confidence = max(0.5, 1.0 - (dist_nm / sensor_range) * 0.5)

                    # Upsert IntelTrackORM
                    existing = await db_session.execute(
                        select(IntelTrackORM).where(
                            IntelTrackORM.session_id == uuid.UUID(self._game_id),
                            IntelTrackORM.target_platform_id == uuid.UUID(target.id),
                        )
                    )
                    track = existing.scalar_one_or_none()

                    if track:
                        track.last_position_lon = target.pos_lon
                        track.last_position_lat = target.pos_lat
                        track.last_updated_tick = tick
                        track.confidence = confidence
                        track.estimated_heading = target.heading
                        track.estimated_speed = target.speed_knots
                        result.tracks_updated += 1
                    else:
                        track = IntelTrackORM(
                            session_id=uuid.UUID(self._game_id),
                            target_platform_id=uuid.UUID(target.id),
                            faction_observer="US",
                            track_type="CONFIRMED" if confidence > 0.8 else "PROBABLE",
                            last_position_lon=target.pos_lon,
                            last_position_lat=target.pos_lat,
                            last_updated_tick=tick,
                            confidence=confidence,
                            estimated_heading=target.heading,
                            estimated_speed=target.speed_knots,
                            platform_type_estimate=target.type_key,
                            source=f"ISR:{isr_p.type_key}",
                        )
                        db_session.add(track)
                        result.tracks_created += 1

                    result.intel_events.append({
                        "id": str(track.id) if hasattr(track, 'id') and track.id else str(uuid.uuid4()),
                        "track_type": "CONFIRMED" if confidence > 0.8 else "PROBABLE",
                        "position": [target.pos_lon, target.pos_lat],
                        "confidence": confidence,
                        "estimated_heading": target.heading,
                        "estimated_speed": target.speed_knots,
                        "platform_type_estimate": target.type_key,
                        "last_updated_tick": tick,
                        "source": f"ISR:{isr_p.type_key}",
                        "faction_observer": "US",
                    })

            await db_session.commit()
        except Exception as exc:
            log.error("ISRSubsystem.resolve_tick error (game=%s, tick=%d): %s", self._game_id, tick, exc)

        return result
