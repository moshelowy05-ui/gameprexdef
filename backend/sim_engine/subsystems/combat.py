"""
CombatSubsystem — detection pass + engagement resolution.

Detection model (per tick):
  Radar sensors (SHIP, AIRCRAFT, UAV, FACILITY) scan enemies in RADAR_RANGE_NM[category].
  ASW sensors (P-8A aircraft type_key contains "P8", ships) detect submarines in SONAR_RANGE_NM.
  Submarines: NOT detectable by radar; only by ASW platforms.

Engagement model (per tick):
  Each armed platform that detected an enemy can fire once per tick.
  Cooldown: each platform tracks last_tick_fired; must wait COOLDOWN_TICKS = 3.
  Roll: random float vs PK_TABLE[(attacker_cat, target_cat)]
  Hit: apply DAMAGE[(attacker_cat, target_cat)] to target.health
  health <= 0 → status = "DESTROYED", speed_knots = 0, is_dirty = True

Max engagements per tick: 20 (prevent log flooding)
"""
from __future__ import annotations

import logging
import random
from typing import NamedTuple

from sim_engine.models import (
    PlatformDelta,
    PlatformHotState,
    SimEvent,
    SimEventType,
)
from sim_engine.subsystems.movement import haversine_nm

log = logging.getLogger(__name__)

# ── Category constants ────────────────────────────────────────────────────────

_SUBMARINE_PREFIXES = ("SSN_", "SSBN_", "SSK_", "TYPE093", "TYPE094", "TYPE039")
_SHIP_PREFIXES = (
    "CVN_", "DDG_", "CG_", "LHA_", "LHD_", "FFG_",
    "TYPE055", "TYPE052", "TYPE071", "TYPE054",
)
_AIRCRAFT_PREFIXES = (
    "F35", "F22", "F15", "F16", "FA18", "B21", "B52", "B1",
    "E2", "P8", "KC", "C17", "J20", "J16", "J11", "H6", "KJ",
)
_UAV_PREFIXES = ("MQ", "RQ", "TB")
_FACILITY_PREFIXES = ("THAAD", "PAC", "HIMARS", "HHQ", "DF", "YJ", "S400", "PATRIOT")


def _category(type_key: str) -> str:
    """Map a platform type_key to its combat category string."""
    tk = type_key.upper()
    for prefix in _SUBMARINE_PREFIXES:
        if tk.startswith(prefix.upper()):
            return "SUBMARINE"
    for prefix in _SHIP_PREFIXES:
        if tk.startswith(prefix.upper()):
            return "SHIP"
    if tk.startswith("LCS"):
        return "SHIP"
    for prefix in _AIRCRAFT_PREFIXES:
        if tk.startswith(prefix.upper()):
            return "AIRCRAFT"
    for prefix in _UAV_PREFIXES:
        if tk.startswith(prefix.upper()):
            return "UAV"
    for prefix in _FACILITY_PREFIXES:
        if tk.startswith(prefix.upper()):
            return "FACILITY"
    return "UNKNOWN"


# ── Range / probability tables ────────────────────────────────────────────────

RADAR_RANGE_NM: dict[str, float] = {
    "SHIP": 200,
    "AIRCRAFT": 150,
    "UAV": 80,
    "FACILITY": 300,
    "SUBMARINE": 0,
    "UNKNOWN": 50,
}

SONAR_RANGE_NM: dict[str, float] = {
    "AIRCRAFT": 50,
    "SHIP": 30,
    "SUBMARINE": 40,
}

WEAPON_RANGE_NM: dict[tuple[str, str], float] = {
    ("SHIP", "SHIP"):           150,
    ("SHIP", "AIRCRAFT"):       80,
    ("SHIP", "SUBMARINE"):      0,    # Ships can't engage subs directly
    ("AIRCRAFT", "SHIP"):       80,
    ("AIRCRAFT", "AIRCRAFT"):   60,
    ("AIRCRAFT", "FACILITY"):   200,
    ("AIRCRAFT", "SUBMARINE"):  30,
    ("SUBMARINE", "SHIP"):      25,
    ("FACILITY", "AIRCRAFT"):   150,
    ("FACILITY", "SHIP"):       0,
    ("UAV", "SHIP"):            30,
    ("UAV", "FACILITY"):        50,
}

PK_TABLE: dict[tuple[str, str], float] = {
    ("SHIP", "SHIP"):           0.35,
    ("SHIP", "AIRCRAFT"):       0.60,
    ("AIRCRAFT", "SHIP"):       0.30,
    ("AIRCRAFT", "AIRCRAFT"):   0.55,
    ("AIRCRAFT", "FACILITY"):   0.40,
    ("AIRCRAFT", "SUBMARINE"):  0.45,
    ("SUBMARINE", "SHIP"):      0.50,
    ("FACILITY", "AIRCRAFT"):   0.70,
    ("UAV", "SHIP"):            0.20,
    ("UAV", "FACILITY"):        0.25,
}

DAMAGE_BY_TYPE: dict[tuple[str, str], float] = {
    ("SHIP", "SHIP"):           0.35,
    ("SHIP", "AIRCRAFT"):       0.80,
    ("AIRCRAFT", "SHIP"):       0.30,
    ("AIRCRAFT", "AIRCRAFT"):   0.85,
    ("AIRCRAFT", "FACILITY"):   0.20,
    ("AIRCRAFT", "SUBMARINE"):  0.55,
    ("SUBMARINE", "SHIP"):      0.45,
    ("FACILITY", "AIRCRAFT"):   0.80,
    ("UAV", "SHIP"):            0.20,
    ("UAV", "FACILITY"):        0.15,
}

_ADVERSARY_FACTIONS = {"ADVERSARY_A", "ADVERSARY_B", "PLAN"}


# ── Result type ───────────────────────────────────────────────────────────────

class CombatTickResult(NamedTuple):
    engagements: int
    hits: int
    kills: int
    detections: int
    deltas: list[PlatformDelta]
    events: list[SimEvent]
    engagements_detail: list[dict]   # raw data for WebSocket broadcast
    intel_updates: list[dict]        # detected enemy positions


# ── Subsystem ─────────────────────────────────────────────────────────────────

class CombatSubsystem:
    COOLDOWN_TICKS = 3
    MAX_ENGAGEMENTS_PER_TICK = 20

    def __init__(self, game_id: str) -> None:
        self._game_id = game_id
        self._last_fired: dict[str, int] = {}   # platform_id → last tick fired

    # ── Public interface ──────────────────────────────────────────────────────

    def resolve_tick(
        self,
        platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> CombatTickResult:
        """Run one combat tick: detection pass + engagement resolution."""

        # ── 1. Faction separation ─────────────────────────────────────────────
        us_ids: set[str] = set()
        adv_ids: set[str] = set()
        for pid, p in platforms.items():
            if p.faction == "US":
                us_ids.add(pid)
            elif p.faction in _ADVERSARY_FACTIONS:
                adv_ids.add(pid)

        # ── 2. Detection pass ─────────────────────────────────────────────────
        # detected_contacts: attacker_id → list of detected enemy platform_ids
        detected_contacts: dict[str, list[str]] = {}
        intel_updates: list[dict] = []

        all_active = {
            pid: p for pid, p in platforms.items()
            if p.status not in ("DESTROYED", "RETIRED", "IN_PRODUCTION")
        }

        for attacker_id, attacker in all_active.items():
            attacker_cat = _category(attacker.type_key)
            enemies = adv_ids if attacker_id in us_ids else us_ids

            contacts: list[str] = []

            # Radar scan (non-submarines only)
            if attacker_cat != "SUBMARINE":
                radar_range = RADAR_RANGE_NM.get(attacker_cat, 50)
                for enemy_id in enemies:
                    enemy = all_active.get(enemy_id)
                    if enemy is None:
                        continue
                    enemy_cat = _category(enemy.type_key)
                    if enemy_cat == "SUBMARINE":
                        continue  # submarines not visible to radar
                    dist = haversine_nm(
                        attacker.pos_lon, attacker.pos_lat,
                        enemy.pos_lon, enemy.pos_lat,
                    )
                    if dist <= radar_range:
                        contacts.append(enemy_id)
                        intel_updates.append({
                            "id": f"track-{enemy_id[:8]}",
                            "target_platform_id": enemy_id,
                            "faction_observer": attacker.faction,
                            "track_type": "CONFIRMED",
                            "position": [enemy.pos_lon, enemy.pos_lat],
                            "estimated_heading": enemy.heading,
                            "estimated_speed": enemy.speed_knots,
                            "platform_type_estimate": enemy.type_key,
                            "confidence": 0.9,
                            "source": "RADAR",
                            "last_updated_tick": tick,
                        })

            # ASW / sonar scan — P-8 aircraft and ships detect enemy submarines
            is_asw_capable = (
                "P8" in attacker.type_key.upper()
                or attacker_cat == "SHIP"
            )
            if is_asw_capable and attacker_cat in SONAR_RANGE_NM:
                sonar_range = SONAR_RANGE_NM[attacker_cat]
                for enemy_id in enemies:
                    if enemy_id in contacts:
                        continue
                    enemy = all_active.get(enemy_id)
                    if enemy is None:
                        continue
                    if _category(enemy.type_key) != "SUBMARINE":
                        continue
                    dist = haversine_nm(
                        attacker.pos_lon, attacker.pos_lat,
                        enemy.pos_lon, enemy.pos_lat,
                    )
                    if dist <= sonar_range:
                        contacts.append(enemy_id)
                        intel_updates.append({
                            "id": f"track-{enemy_id[:8]}",
                            "target_platform_id": enemy_id,
                            "faction_observer": attacker.faction,
                            "track_type": "CONFIRMED",
                            "position": [enemy.pos_lon, enemy.pos_lat],
                            "estimated_heading": enemy.heading,
                            "estimated_speed": enemy.speed_knots,
                            "platform_type_estimate": enemy.type_key,
                            "confidence": 0.9,
                            "source": "SONAR",
                            "last_updated_tick": tick,
                        })

            if contacts:
                detected_contacts[attacker_id] = contacts

        total_detections = sum(len(v) for v in detected_contacts.values())

        # ── 3. Engagement pass ────────────────────────────────────────────────
        # Sort by number of detected enemies (most contacts first = higher priority)
        sorted_attackers = sorted(
            detected_contacts.keys(),
            key=lambda pid: len(detected_contacts[pid]),
            reverse=True,
        )

        engagement_count = 0
        hit_count = 0
        kill_count = 0
        engagements_detail: list[dict] = []
        modified_platform_ids: set[str] = set()

        for attacker_id in sorted_attackers:
            if engagement_count >= self.MAX_ENGAGEMENTS_PER_TICK:
                break

            attacker = all_active.get(attacker_id)
            if attacker is None:
                continue
            if attacker.status == "DESTROYED" or attacker.fuel_state <= 0.005:
                continue

            # Cooldown check
            last_fired = self._last_fired.get(attacker_id, -999)
            if (tick - last_fired) < self.COOLDOWN_TICKS:
                continue

            attacker_cat = _category(attacker.type_key)
            contact_ids = detected_contacts[attacker_id]

            # Find closest detected enemy within weapon range
            best_target_id: str | None = None
            best_dist: float = float("inf")

            for target_id in contact_ids:
                target = all_active.get(target_id)
                if target is None or target.status == "DESTROYED":
                    continue
                target_cat = _category(target.type_key)
                weapon_range = WEAPON_RANGE_NM.get((attacker_cat, target_cat), 0)
                if weapon_range <= 0:
                    continue
                dist = haversine_nm(
                    attacker.pos_lon, attacker.pos_lat,
                    target.pos_lon, target.pos_lat,
                )
                if dist <= weapon_range and dist < best_dist:
                    best_dist = dist
                    best_target_id = target_id

            if best_target_id is None:
                continue

            target = platforms[best_target_id]
            target_cat = _category(target.type_key)
            pk = PK_TABLE.get((attacker_cat, target_cat), 0.0)
            damage = DAMAGE_BY_TYPE.get((attacker_cat, target_cat), 0.0)

            roll = random.random()
            hit = roll < pk

            if hit:
                target.health = max(0.0, target.health - damage)
                target.is_dirty = True
                hit_count += 1
                modified_platform_ids.add(best_target_id)

                if target.health <= 0.0:
                    target.status = "DESTROYED"
                    target.speed_knots = 0.0
                    kill_count += 1
                    log.info(
                        "TICK %d | KILL: %s (%s) destroyed by %s (%s) at %.1f NM",
                        tick, target.type_key, target.faction,
                        attacker.type_key, attacker.faction, best_dist,
                    )

            self._last_fired[attacker_id] = tick
            engagement_count += 1

            detail: dict = {
                "tick": tick,
                "attacker_id": attacker_id,
                "target_id": best_target_id,
                "attacker_faction": attacker.faction,
                "weapon_type": f"{attacker_cat}_WEAPON",
                "distance_nm": round(best_dist, 1),
                "hit": hit,
                "damage": round(damage, 2) if hit else 0.0,
                "target_health_after": round(target.health, 3),
                "narrative": (
                    f"{'HIT' if hit else 'MISS'}: {attacker.type_key} ({attacker.faction}) "
                    f"engages {target.type_key} at {round(best_dist, 0)} NM"
                ),
            }
            engagements_detail.append(detail)

            log.debug(
                "TICK %d | %s: %s (%s) → %s (%s) %.1f NM pk=%.2f roll=%.3f dmg=%.2f",
                tick,
                "HIT" if hit else "MISS",
                attacker.type_key, attacker.faction,
                target.type_key, target.faction,
                best_dist, pk, roll, damage if hit else 0.0,
            )

        # ── 4. Build PlatformDeltas for modified platforms ─────────────────────
        deltas: list[PlatformDelta] = []
        events: list[SimEvent] = []

        for pid in modified_platform_ids:
            p = platforms[pid]
            delta = PlatformDelta(
                id=pid,
                health=round(p.health, 3),
                status=p.status if p.status == "DESTROYED" else None,
                speed=0.0 if p.status == "DESTROYED" else None,
            )
            deltas.append(delta)

            if p.status == "DESTROYED":
                events.append(SimEvent(
                    type=SimEventType.PLATFORM_STATUS_CHANGE,
                    tick=tick,
                    platform_id=pid,
                    game_id=self._game_id,
                    data={"new_status": "DESTROYED", "health": p.health},
                    narrative=f"{p.type_key} ({p.faction}) has been destroyed",
                ))

        return CombatTickResult(
            engagements=engagement_count,
            hits=hit_count,
            kills=kill_count,
            detections=len(detected_contacts),
            deltas=deltas,
            events=events,
            engagements_detail=engagements_detail,
            intel_updates=intel_updates,
        )
