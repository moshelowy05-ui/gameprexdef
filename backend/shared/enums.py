from enum import StrEnum


class Faction(StrEnum):
    US = "US"
    ADVERSARY_A = "ADVERSARY_A"  # Near-peer Pacific adversary
    ADVERSARY_B = "ADVERSARY_B"  # Regional Middle East adversary
    NEUTRAL = "NEUTRAL"


class PlatformClass(StrEnum):
    SHIP = "SHIP"
    AIRCRAFT = "AIRCRAFT"
    MISSILE = "MISSILE"
    SATELLITE = "SATELLITE"
    VEHICLE = "VEHICLE"
    FACILITY = "FACILITY"
    SUBMARINE = "SUBMARINE"
    UAV = "UAV"


class PlatformStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DESTROYED = "DESTROYED"
    IN_TRANSIT = "IN_TRANSIT"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE"
    IN_PRODUCTION = "IN_PRODUCTION"
    DOCKED = "DOCKED"
    AIRBORNE = "AIRBORNE"
    SUBMERGED = "SUBMERGED"
    RETIRED = "RETIRED"


class MissionType(StrEnum):
    STRIKE = "STRIKE"
    PATROL = "PATROL"
    INTERCEPT = "INTERCEPT"
    RECON = "RECON"
    ESCORT = "ESCORT"
    SEAD = "SEAD"           # Suppression of Enemy Air Defenses
    CAS = "CAS"             # Close Air Support
    ASW = "ASW"             # Anti-Submarine Warfare
    AAW = "AAW"             # Anti-Air Warfare
    ASUW = "ASUW"           # Anti-Surface Warfare
    LOGISTICS = "LOGISTICS"
    ISR = "ISR"             # Intelligence, Surveillance, Reconnaissance
    EW = "EW"               # Electronic Warfare


class MissionStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    ABORTED = "ABORTED"
    FAILED = "FAILED"
    SUSPENDED = "SUSPENDED"


class FacilityType(StrEnum):
    SHIPYARD = "SHIPYARD"
    AIRCRAFT_FACTORY = "AIRCRAFT_FACTORY"
    MISSILE_PLANT = "MISSILE_PLANT"
    MUNITIONS_DEPOT = "MUNITIONS_DEPOT"
    AIRBASE = "AIRBASE"
    NAVAL_BASE = "NAVAL_BASE"
    C2_NODE = "C2_NODE"
    RADAR_SITE = "RADAR_SITE"
    FUEL_DEPOT = "FUEL_DEPOT"
    MAINTENANCE_FACILITY = "MAINTENANCE_FACILITY"
    SPACE_LAUNCH_FACILITY = "SPACE_LAUNCH_FACILITY"


class TaskForceStatus(StrEnum):
    ASSEMBLING = "ASSEMBLING"
    READY = "READY"
    UNDERWAY = "UNDERWAY"
    ENGAGED = "ENGAGED"
    DISPERSED = "DISPERSED"
    RETURNED = "RETURNED"


class CombatEventType(StrEnum):
    DETECTION = "DETECTION"
    ENGAGEMENT = "ENGAGEMENT"
    INTERCEPT = "INTERCEPT"
    HIT = "HIT"
    MISS = "MISS"
    DESTRUCTION = "DESTRUCTION"
    WITHDRAWAL = "WITHDRAWAL"
    MALFUNCTION = "MALFUNCTION"
    LAUNCH = "LAUNCH"
    SPLASH = "SPLASH"


class WeaponReleaseAuthority(StrEnum):
    AUTONOMOUS = "AUTONOMOUS"
    COMMANDER = "COMMANDER"
    NCA = "NCA"  # National Command Authority


class IntelTrackType(StrEnum):
    CONFIRMED = "CONFIRMED"
    PROBABLE = "PROBABLE"
    POSSIBLE = "POSSIBLE"
    GHOST = "GHOST"


class IntelSource(StrEnum):
    RADAR = "RADAR"
    SIGINT = "SIGINT"
    HUMINT = "HUMINT"
    SATELLITE = "SATELLITE"
    ACOUSTIC = "ACOUSTIC"
    VISUAL = "VISUAL"
    DATALINK = "DATALINK"


class PowerState(StrEnum):
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
