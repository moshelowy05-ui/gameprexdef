"""
ISRSubsystem — Intelligence, Surveillance, Reconnaissance.

Each tick: all US platforms with radar/sonar scan for adversary units within
their sensor range and upsert IntelTrackORM entries. This drives the Fog of
War on the frontend — enemies are only visible if tracked here.

Sensor ranges (NM) by platform category mirror the combat.py detection model:
  Ships: 200 NM surface radar
  Aircraft: 150 NM airborne radar
  UAV: 80 NM
  Facility: 300 NM ground radar
  Dedicated ISR (P-8A, E-2D, RQ-4): longer ranges per type_key override

Submarines do not emit radar (stealthy) and are only detected by ASW assets.
"""
from __future__ import annotations
import logging
import math
import uuid
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Per-category default radar ranges (NM) — matches frontend SENSOR_RANGE_NM
CATEGORY_RADAR_RANGE_NM: dict[str, float] = {
    "SHIP":       200.0,
    "AIRCRAFT":   150.0,
    "UAV":        80.0,
    "FACILITY":   300.0,
    "VEHICLE":    30.0,
    "SUBMARINE":  0.0,   # subs are stealthy
    "MISSILE":    0.0,
}

# Type-key overrides for dedicated ISR platforms (higher range than category default)
ISR_TYPE_OVERRIDES: dict[str, float] = {
    "P8A":  350.0,   # P-8A Poseidon maritime patrol
    "E2D":  300.0,   # E-2D Advanced Hawkeye AEW
    "RQ4":  450.0,   # RQ-4 Global Hawk SIGINT/IMINT
    "EP3":  250.0,   # EP-3E Aries SIGINT
}

# ASW platforms that can detect submarines
ASW_PLATFORM_PREFIXES = ("P8", "E2", "DDG_", "CG_", "FFG_", "SSN_")
ASW_RANGE_NM = 80.0

# How often ISR reports (every N ticks) — keep low so FoW updates responsively
ISR_REPORT_INTERVAL = 2


def _category(type_key: str) -> str:
    tk = type_key.upper()
    sub_prefixes = ("SSN_", "SSBN_", "SSK_", "TYPE093", "TYPE094", "TYPE039")
    ship_prefixes = ("CVN_", "DDG_", "CG_", "LHA_", "LHD_", "FFG_", "LCS",
                     "TYPE055", "TYPE052", "TYPE071", "TYPE054")
    air_prefixes = ("F35", "F22", "F15", "F16", "FA18", "B21", "B52", "B1",
                    "E2", "P8", "KC", "C17", "J20", "J16", "J11", "H6", "KJ")
    uav_prefixes = ("MQ", "RQ", "TB")
    fac_prefixes = ("THAAD", "PAC", "HIMARS", "HHQ", "DF", "YJ", "S400", "PATRIOT")
    for p in sub_prefixes:
        if tk.startswith(p.upper()): return "SUBMARINE"
    for p in ship_prefixes:
        if tk.startswith(p.upper()): return "SHIP"
    for p in air_prefixes:
        if tk.startswith(p.upper()): return "AIRCRAFT"
    for p in uav_prefixes:
        if tk.startswith(p.upper()): return "UAV"
    for p in fac_prefixes:
        if tk.startswith(p.upper()): return "FACILITY"
    return "UNKNOWN"


def _sensor_range_nm(type_key: str) -> float:
    """Return sensor range in NM for a given platform type_key."""
    tk_upper = type_key.upper()
    for prefix, rng in ISR_TYPE_OVERRIDES.items():
        if tk_upper.startswith(prefix.upper()):
            return rng
    cat = _category(type_key)
    return CATEGORY_RADAR_RANGE_NM.get(cat, 0.0)


def _is_asw(type_key: str) -> bool:
    tk = type_key.upper()
    return any(tk.startswith(p.upper()) for p in ASW_PLATFORM_PREFIXES)


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


@dataclass
class ISRTickResult:
    tracks_created: int = 0
    tracks_updated: int = 0
    intel_events: list[dict] = field(default_factory=list)


class ISRSubsystem:
    def __init__(self, game_id: str) -> None:
        self._game_id = game_id

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

            # All active US platforms
            us_platforms = [
                p for p in platforms.values()
                if p.faction == "US"
                and p.status not in ("DESTROYED", "RETIRED", "IN_PRODUCTION")
                and p.pos_lat is not None
                and p.pos_lon is not None
            ]

            if not us_platforms:
                return result

            # All adversary platforms (include submarines for ASW detection)
            adversary = [
                p for p in platforms.values()
                if p.faction in ("ADVERSARY_A", "PLAN")
                and p.status not in ("DESTROYED", "RETIRED")
                and p.pos_lat is not None
                and p.pos_lon is not None
            ]

            if not adversary:
                return result

            # Build a cache of existing tracks for efficient upsert
            existing_tracks_result = await db_session.execute(
                select(IntelTrackORM).where(
                    IntelTrackORM.session_id == uuid.UUID(self._game_id)
                )
            )
            track_by_platform: dict[str, IntelTrackORM] = {
                str(t.target_platform_id): t
                for t in existing_tracks_result.scalars().all()
                if t.target_platform_id is not None
            }

            # Determine best detection for each adversary platform
            best: dict[str, tuple[float, str]] = {}  # platform_id → (confidence, source)

            for us in us_platforms:
                radar_range = _sensor_range_nm(us.type_key)
                asw = _is_asw(us.type_key)

                for target in adversary:
                    is_submarine = _category(target.type_key) == "SUBMARINE"

                    # Submarines only detected by ASW platforms
                    if is_submarine and not asw:
                        continue
                    if is_submarine:
                        detect_range = ASW_RANGE_NM
                    else:
                        detect_range = radar_range

                    if detect_range <= 0:
                        continue

                    dist_nm = _haversine_nm(us.pos_lat, us.pos_lon, target.pos_lat, target.pos_lon)
                    if dist_nm > detect_range:
                        continue

                    confidence = max(0.3, 1.0 - (dist_nm / detect_range) * 0.6)
                    source_key = f"{us.type_key[:8]}"

                    prev = best.get(target.id)
                    if prev is None or confidence > prev[0]:
                        best[target.id] = (confidence, source_key)

            # Upsert tracks
            for target in adversary:
                if target.id not in best:
                    continue
                confidence, source = best[target.id]
                track_type = "CONFIRMED" if confidence > 0.75 else "PROBABLE" if confidence > 0.45 else "POSSIBLE"

                track = track_by_platform.get(target.id)
                if track:
                    track.last_position_lon = target.pos_lon
                    track.last_position_lat = target.pos_lat
                    track.last_updated_tick = tick
                    track.confidence = confidence
                    track.track_type = track_type
                    track.estimated_heading = target.heading
                    track.estimated_speed = target.speed_knots
                    result.tracks_updated += 1
                else:
                    track = IntelTrackORM(
                        session_id=uuid.UUID(self._game_id),
                        target_platform_id=uuid.UUID(target.id),
                        faction_observer="US",
                        track_type=track_type,
                        last_position_lon=target.pos_lon,
                        last_position_lat=target.pos_lat,
                        last_updated_tick=tick,
                        confidence=confidence,
                        estimated_heading=target.heading,
                        estimated_speed=target.speed_knots,
                        platform_type_estimate=target.type_key,
                        source=source,
                    )
                    db_session.add(track)
                    track_by_platform[target.id] = track
                    result.tracks_created += 1

                result.intel_events.append({
                    "id": str(getattr(track, "id", None) or uuid.uuid4()),
                    "target_platform_id": target.id,
                    "track_type": track_type,
                    "last_position": [target.pos_lon, target.pos_lat],
                    "confidence": confidence,
                    "estimated_heading": target.heading,
                    "estimated_speed": target.speed_knots,
                    "platform_type_estimate": target.type_key,
                    "last_updated_tick": tick,
                    "source": source,
                    "faction_observer": "US",
                })

            await db_session.commit()

        except Exception as exc:
            log.error("ISRSubsystem.resolve_tick error (game=%s, tick=%d): %s", self._game_id, tick, exc)

        return result
