"""
CombatSubsystem — detection pass + engagement resolution.

Detection model (per tick):
  Radar sensors (SHIP, AIRCRAFT, UAV, FACILITY) scan enemies in RADAR_RANGE_NM[category].
  ASW sensors (P-8A aircraft and ships) detect submarines in SONAR_RANGE_NM.
  Submarines: NOT detectable by radar; only by ASW platforms.
  ASBM/cruise missile batteries: detect ships via OTH-relay (long-range datalink from PLAN AEW).

Engagement model (per tick):
  Each armed platform that detected an enemy fires once per tick (cooldown applies).
  Weapon ranges and Pk values are platform-specific for missile systems.
  ASBM (DF-21D, DF-26): engage ships at long range, lower Pk vs moving targets.
  Coastal missiles (YJ-18): engage ships at medium range.
  SAMs (HHQ-9, THAAD, PAC-3): engage aircraft/cruise missiles at medium range.
  Cooldown: COOLDOWN_TICKS ticks between shots.
  Kill: health ≤ 0 → status = DESTROYED.

Max engagements per tick: 30.
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
    "CVN_", "DDG_", "CG_", "LHA_", "LHD_", "LPD_", "FFG_", "T_AO",
    "TYPE055", "TYPE052", "TYPE071", "TYPE054", "TYPE075",
)
_AIRCRAFT_PREFIXES = (
    "F35", "F22", "F15", "F16", "FA18", "EA18", "B21", "B52", "B1",
    "E2", "P8", "KC", "C17", "J20", "J16", "J11", "H6", "KJ", "WZ",
)
_UAV_PREFIXES = ("MQ", "RQ", "TB", "WZ7")
_FACILITY_PREFIXES = ("THAAD", "PAC", "HIMARS", "HHQ", "DF", "YJ", "S400", "PATRIOT")
_ADVERSARY_FACTIONS = {"ADVERSARY_A", "ADVERSARY_B", "PLAN"}


def _category(type_key: str) -> str:
    tk = type_key.upper()
    for prefix in _SUBMARINE_PREFIXES:
        if tk.startswith(prefix.upper()): return "SUBMARINE"
    for prefix in _SHIP_PREFIXES:
        if tk.startswith(prefix.upper()): return "SHIP"
    if tk.startswith("LCS"): return "SHIP"
    for prefix in _AIRCRAFT_PREFIXES:
        if tk.startswith(prefix.upper()): return "AIRCRAFT"
    for prefix in _UAV_PREFIXES:
        if tk.startswith(prefix.upper()): return "UAV"
    for prefix in _FACILITY_PREFIXES:
        if tk.startswith(prefix.upper()): return "FACILITY"
    return "UNKNOWN"


# ── Range / probability tables ────────────────────────────────────────────────

RADAR_RANGE_NM: dict[str, float] = {
    "SHIP":      200,
    "AIRCRAFT":  150,
    "UAV":       80,
    "FACILITY":  300,
    "SUBMARINE": 0,
    "UNKNOWN":   50,
}

SONAR_RANGE_NM: dict[str, float] = {
    "AIRCRAFT": 50,
    "SHIP":     30,
    "SUBMARINE": 40,
}

# Baseline weapon ranges — overridden per type_key for missile systems
_WEAPON_RANGE_BASE: dict[tuple[str, str], float] = {
    ("SHIP", "SHIP"):           150,   # SM-6 / LRASM baseline
    ("SHIP", "AIRCRAFT"):       80,    # SM-6 AAW
    ("SHIP", "SUBMARINE"):      0,
    ("AIRCRAFT", "SHIP"):       200,   # LRASM / AGM-158C stand-off
    ("AIRCRAFT", "AIRCRAFT"):   60,    # AIM-120D AMRAAM
    ("AIRCRAFT", "FACILITY"):   300,   # JASSM-ER / SDB II
    ("AIRCRAFT", "SUBMARINE"):  30,    # MK-54 torpedo / HAAWC
    ("SUBMARINE", "SHIP"):      25,    # Mk 48 ADCAP / Yu-6 torpedo
    ("FACILITY", "AIRCRAFT"):   0,     # overridden per type_key (SAMs)
    ("FACILITY", "SHIP"):       0,     # overridden per type_key (ASBMs/coastals)
    ("UAV", "SHIP"):            30,
    ("UAV", "FACILITY"):        50,
}

# ── Per type_key weapon profiles ──────────────────────────────────────────────
# Each entry: (weapon_range_nm, pk_vs_target, damage_per_hit, weapon_name)
# type_key prefix → {target_category: (range_nm, pk, damage, name)}
_TYPE_KEY_WEAPONS: dict[str, dict[str, tuple[float, float, float, str]]] = {
    # ── PLAN ballistic / cruise missiles ──────────────────────────────────────
    "DF21D":  {"SHIP": (810.0,  0.18, 0.65, "DF-21D ASBM")},   # carrier killer, CEP ~20m
    "DF26":   {"SHIP": (1500.0, 0.12, 0.75, "DF-26B ASBM")},   # IRBM — longest reach
    "YJ18":   {
        "SHIP":     (290.0, 0.35, 0.40, "YJ-18 anti-ship missile"),
        "FACILITY": (290.0, 0.30, 0.35, "YJ-18 cruise missile"),
    },
    "HHQ9":   {"AIRCRAFT": (108.0, 0.55, 0.80, "HHQ-9 SAM")},
    "HHQ16":  {"AIRCRAFT": (54.0,  0.50, 0.80, "HHQ-16 SAM")},
    # ── US missile systems ────────────────────────────────────────────────────
    "THAAD":  {"AIRCRAFT": (120.0, 0.80, 0.95, "THAAD interceptor")},   # vs ballistic
    "PAC3":   {"AIRCRAFT": (35.0,  0.85, 0.90, "PAC-3 MSE")},
    "HIMARS": {
        "FACILITY": (190.0, 0.60, 0.40, "ATACMS"),
        "SHIP":     (190.0, 0.30, 0.40, "ATACMS"),
    },
    "PATRIOT": {"AIRCRAFT": (60.0, 0.75, 0.90, "PAC-2 GEM-T")},
}


# ── Magazine sizes (number of engagement salvos before winchester) ────────────
# Each engagement consumes one salvo → depletes weapons_remaining by 1/size.
# Type-key prefixes checked first (specific), then category fallback.
_MAGAZINE_BY_TYPE: dict[str, int] = {
    "DF21":  6,    # limited ASBM stock — high-value, few rounds
    "DF26":  6,
    "YJ18":  8,    # coastal anti-ship battery reloads
    "THAAD": 18,   # deep interceptor magazine
    "PAC3":  16,
    "HHQ9":  16,
    "HHQ16": 12,
    "PATRIOT": 16,
    "HIMARS": 12,
    "B21":   8,    # bomber deep magazine (rotary launcher)
    "B52":   12,
    "B1":    12,
    "H6":    6,    # H-6K cruise missile load
}
_MAGAZINE_BY_CATEGORY: dict[str, int] = {
    "SHIP":      12,   # VLS cells — meaningful engagement salvos
    "SUBMARINE": 6,    # torpedo tubes + reloads
    "AIRCRAFT":  4,    # hardpoints — then RTB to rearm
    "UAV":       2,
    "FACILITY":  10,
    "UNKNOWN":   4,
}


def _magazine_size(type_key: str, category: str) -> int:
    tk = type_key.upper()
    for prefix, size in _MAGAZINE_BY_TYPE.items():
        if tk.startswith(prefix.upper()):
            return size
    return _MAGAZINE_BY_CATEGORY.get(category, 4)


def _resolve_weapon(
    attacker_type_key: str,
    attacker_cat: str,
    target_cat: str,
) -> tuple[float, float, float, str]:
    """Return (range_nm, pk, damage, weapon_name) for this engagement pairing."""
    tk = attacker_type_key.upper()
    for prefix, profiles in _TYPE_KEY_WEAPONS.items():
        if tk.startswith(prefix.upper()):
            profile = profiles.get(target_cat)
            if profile:
                return profile
            # Weapon exists but can't engage this category
            return (0.0, 0.0, 0.0, "no weapon")

    # Fall back to baseline tables
    base_range = _WEAPON_RANGE_BASE.get((attacker_cat, target_cat), 0.0)
    if base_range == 0.0:
        return (0.0, 0.0, 0.0, "no weapon")

    # Default Pk and damage
    _PK_BASE: dict[tuple[str, str], float] = {
        ("SHIP", "SHIP"):         0.30,
        ("SHIP", "AIRCRAFT"):     0.60,
        ("AIRCRAFT", "SHIP"):     0.35,
        ("AIRCRAFT", "AIRCRAFT"): 0.55,
        ("AIRCRAFT", "FACILITY"): 0.40,
        ("AIRCRAFT", "SUBMARINE"): 0.45,
        ("SUBMARINE", "SHIP"):    0.50,
        ("UAV", "SHIP"):          0.20,
        ("UAV", "FACILITY"):      0.25,
    }
    _DMG_BASE: dict[tuple[str, str], float] = {
        ("SHIP", "SHIP"):         0.35,
        ("SHIP", "AIRCRAFT"):     0.80,
        ("AIRCRAFT", "SHIP"):     0.30,
        ("AIRCRAFT", "AIRCRAFT"): 0.85,
        ("AIRCRAFT", "FACILITY"): 0.25,
        ("AIRCRAFT", "SUBMARINE"): 0.55,
        ("SUBMARINE", "SHIP"):    0.45,
        ("UAV", "SHIP"):          0.20,
        ("UAV", "FACILITY"):      0.15,
    }
    _NAMES: dict[tuple[str, str], str] = {
        ("SHIP", "SHIP"):         _weapon_name_ship_vs_ship(attacker_type_key),
        ("SHIP", "AIRCRAFT"):     "SM-6",
        ("AIRCRAFT", "SHIP"):     _weapon_name_air_vs_ship(attacker_type_key),
        ("AIRCRAFT", "AIRCRAFT"): _weapon_name_air_vs_air(attacker_type_key),
        ("AIRCRAFT", "FACILITY"): _weapon_name_air_vs_ground(attacker_type_key),
        ("AIRCRAFT", "SUBMARINE"): "Mk 54 torpedo",
        ("SUBMARINE", "SHIP"):    _weapon_name_sub_vs_ship(attacker_type_key),
        ("UAV", "SHIP"):          "Hellfire",
        ("UAV", "FACILITY"):      "Hellfire",
    }
    pk = _PK_BASE.get((attacker_cat, target_cat), 0.1)
    dmg = _DMG_BASE.get((attacker_cat, target_cat), 0.2)
    name = _NAMES.get((attacker_cat, target_cat), f"{attacker_cat} munition")
    return (base_range, pk, dmg, name)


def _weapon_name_ship_vs_ship(tk: str) -> str:
    t = tk.upper()
    if t.startswith("CVN"): return "LRASM / Harpoon"
    if t.startswith(("DDG", "CG")): return "LRASM / SM-6 ASUW"
    if t.startswith("TYPE055"): return "YJ-18 / HHQ-9 salvo"
    if t.startswith("TYPE052"): return "YJ-18 salvo"
    if t.startswith(("TYPE054", "TYPE075", "TYPE071")): return "YJ-83 salvo"
    return "anti-ship missile"


def _weapon_name_air_vs_ship(tk: str) -> str:
    t = tk.upper()
    if t.startswith(("F35", "FA18")): return "AGM-158C LRASM"
    if t.startswith(("B21", "B52", "B1")): return "JASSM-ER salvo"
    if t.startswith(("J20", "J16")): return "YJ-12 / CM-802AKG"
    if t.startswith("H6"): return "YJ-12B stand-off salvo"
    return "air-launched anti-ship missile"


def _weapon_name_air_vs_air(tk: str) -> str:
    t = tk.upper()
    if t.startswith(("F22", "F35")): return "AIM-120D AMRAAM"
    if t.startswith("FA18"): return "AIM-120C AMRAAM"
    if t.startswith(("J20", "J16", "J11")): return "PL-15 / PL-12"
    if t.startswith("H6"): return "PL-5 (self-defense)"
    return "AAM"


def _weapon_name_air_vs_ground(tk: str) -> str:
    t = tk.upper()
    if t.startswith(("B21", "B52", "B1")): return "JASSM-ER / GBU-57"
    if t.startswith("F35"): return "SDB II / JDAM"
    if t.startswith("EA18"): return "AGM-88E AARGM"
    if t.startswith(("J16", "J20")): return "LS-6 / YJ-91 SEAD"
    return "precision munition"


def _weapon_name_sub_vs_ship(tk: str) -> str:
    t = tk.upper()
    if t.startswith("SSN_") or t.startswith("SSN"): return "Mk 48 ADCAP"
    if t.startswith("TYPE093") or t.startswith("TYPE039"): return "Yu-6 torpedo"
    return "heavyweight torpedo"


# ── Result type ───────────────────────────────────────────────────────────────

class CombatTickResult(NamedTuple):
    engagements: int
    hits: int
    kills: int
    detections: int
    deltas: list[PlatformDelta]
    events: list[SimEvent]
    engagements_detail: list[dict]
    intel_updates: list[dict]


# ── Subsystem ─────────────────────────────────────────────────────────────────

class CombatSubsystem:
    COOLDOWN_TICKS = 3
    MAX_ENGAGEMENTS_PER_TICK = 30

    def __init__(self, game_id: str) -> None:
        self._game_id = game_id
        self._last_fired: dict[str, int] = {}

    def resolve_tick(
        self,
        platforms: dict[str, PlatformHotState],
        tick: int,
    ) -> CombatTickResult:
        """Run one combat tick: detection pass + engagement resolution."""

        us_ids: set[str] = set()
        adv_ids: set[str] = set()
        for pid, p in platforms.items():
            if p.faction == "US":
                us_ids.add(pid)
            elif p.faction in _ADVERSARY_FACTIONS:
                adv_ids.add(pid)

        # ── Detection pass ────────────────────────────────────────────────────
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

            # ASBM / long-range missile batteries use OTH targeting (their own datalink)
            # — detection range matches weapon range so they can fire if in range
            tk_up = attacker.type_key.upper()
            is_asbm = any(tk_up.startswith(p) for p in ("DF21", "DF26", "YJ18", "YJ12"))
            if is_asbm:
                # Use weapon range as detection range (datalink/OTH from AEW)
                for target_cat_check in ("SHIP",):
                    for enemy_id in enemies:
                        enemy = all_active.get(enemy_id)
                        if not enemy: continue
                        if _category(enemy.type_key) != target_cat_check: continue
                        _, _, _, _ = _resolve_weapon(attacker.type_key, "FACILITY", target_cat_check)
                        rng, _, _, _ = _resolve_weapon(attacker.type_key, "FACILITY", target_cat_check)
                        if rng <= 0: continue
                        dist = haversine_nm(attacker.pos_lon, attacker.pos_lat, enemy.pos_lon, enemy.pos_lat)
                        if dist <= rng:
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
                                "confidence": 0.85,
                                "source": "OTH_DATALINK",
                                "last_updated_tick": tick,
                            })
            elif attacker_cat != "SUBMARINE":
                # Standard radar scan
                radar_range = RADAR_RANGE_NM.get(attacker_cat, 50)
                for enemy_id in enemies:
                    enemy = all_active.get(enemy_id)
                    if not enemy: continue
                    if _category(enemy.type_key) == "SUBMARINE": continue
                    dist = haversine_nm(attacker.pos_lon, attacker.pos_lat, enemy.pos_lon, enemy.pos_lat)
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

            # ASW sonar
            is_asw_capable = "P8" in attacker.type_key.upper() or attacker_cat == "SHIP"
            if is_asw_capable and attacker_cat in SONAR_RANGE_NM:
                sonar_range = SONAR_RANGE_NM[attacker_cat]
                for enemy_id in enemies:
                    if enemy_id in contacts: continue
                    enemy = all_active.get(enemy_id)
                    if not enemy: continue
                    if _category(enemy.type_key) != "SUBMARINE": continue
                    dist = haversine_nm(attacker.pos_lon, attacker.pos_lat, enemy.pos_lon, enemy.pos_lat)
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

        # ── Engagement pass ───────────────────────────────────────────────────
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
            if not attacker or attacker.status == "DESTROYED" or attacker.fuel_state <= 0.005:
                continue

            # Winchester — out of weapons, cannot engage until rearmed
            if attacker.weapons_remaining <= 0.0:
                continue

            last_fired = self._last_fired.get(attacker_id, -999)
            if (tick - last_fired) < self.COOLDOWN_TICKS:
                continue

            attacker_cat = _category(attacker.type_key)
            contact_ids = detected_contacts[attacker_id]

            # Find closest enemy within weapon range
            best_target_id: str | None = None
            best_dist: float = float("inf")
            best_weapon: tuple[float, float, float, str] = (0.0, 0.0, 0.0, "")

            for target_id in contact_ids:
                target = all_active.get(target_id)
                if not target or target.status == "DESTROYED": continue
                target_cat = _category(target.type_key)
                weapon = _resolve_weapon(attacker.type_key, attacker_cat, target_cat)
                w_range = weapon[0]
                if w_range <= 0: continue
                dist = haversine_nm(attacker.pos_lon, attacker.pos_lat, target.pos_lon, target.pos_lat)
                if dist <= w_range and dist < best_dist:
                    best_dist = dist
                    best_target_id = target_id
                    best_weapon = weapon

            if best_target_id is None:
                continue

            target = platforms[best_target_id]
            target_cat = _category(target.type_key)
            _, pk, damage, weapon_name = best_weapon

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
                        "TICK %d KILL: %s (%s) destroyed by %s via %s at %.0f NM",
                        tick, target.type_key, target.faction,
                        attacker.type_key, weapon_name, best_dist,
                    )

            self._last_fired[attacker_id] = tick
            engagement_count += 1

            # ── Deplete attacker magazine ──────────────────────────────────────
            mag_size = _magazine_size(attacker.type_key, attacker_cat)
            attacker.weapons_remaining = max(0.0, attacker.weapons_remaining - 1.0 / mag_size)
            attacker.is_dirty = True
            modified_platform_ids.add(attacker_id)
            went_winchester = attacker.weapons_remaining <= 0.0
            if went_winchester:
                log.info(
                    "TICK %d WINCHESTER: %s (%s) expended all weapons",
                    tick, attacker.type_key, attacker.faction,
                )

            detail: dict = {
                "tick": tick,
                "attacker_id": attacker_id,
                "target_id": best_target_id,
                "attacker_faction": attacker.faction,
                "weapon_type": weapon_name,
                "distance_nm": round(best_dist, 1),
                "hit": hit,
                "damage": round(damage, 2) if hit else 0.0,
                "target_health_after": round(target.health, 3),
                "attacker_weapons_remaining": round(attacker.weapons_remaining, 3),
                "attacker_winchester": went_winchester,
                "narrative": _build_narrative(attacker, target, weapon_name, best_dist, hit),
            }
            engagements_detail.append(detail)

            log.debug(
                "TICK %d %s: %s → %s via %s at %.0f NM pk=%.2f roll=%.3f",
                tick, "HIT" if hit else "MISS",
                attacker.type_key, target.type_key, weapon_name, best_dist, pk, roll,
            )

        # ── Build deltas ──────────────────────────────────────────────────────
        deltas: list[PlatformDelta] = []
        events: list[SimEvent] = []

        for pid in modified_platform_ids:
            p = platforms[pid]
            deltas.append(PlatformDelta(
                id=pid,
                health=round(p.health, 3),
                status=p.status if p.status == "DESTROYED" else None,
                speed=0.0 if p.status == "DESTROYED" else None,
                weapons_remaining=round(p.weapons_remaining, 3),
            ))
            if p.status == "DESTROYED":
                events.append(SimEvent(
                    type=SimEventType.PLATFORM_STATUS_CHANGE,
                    tick=tick,
                    platform_id=pid,
                    game_id=self._game_id,
                    data={"new_status": "DESTROYED", "health": p.health},
                    narrative=f"{p.type_key} ({p.faction}) destroyed",
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


def _build_narrative(
    attacker: PlatformHotState,
    target: PlatformHotState,
    weapon_name: str,
    dist_nm: float,
    hit: bool,
) -> str:
    result = "IMPACT" if hit else "MISS"
    faction_a = "US" if attacker.faction == "US" else "PLAN"
    faction_t = "US" if target.faction == "US" else "PLAN"
    return (
        f"{result}: {faction_a} {attacker.type_key} fires {weapon_name} "
        f"at {faction_t} {target.type_key} — {round(dist_nm, 0):.0f} NM"
    )
