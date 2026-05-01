"""
Pydantic v2 domain models — shared source of truth across all backend services.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .enums import (
    CombatEventType,
    Faction,
    FacilityType,
    IntelSource,
    IntelTrackType,
    MissionStatus,
    MissionType,
    PlatformClass,
    PlatformStatus,
    PowerState,
    TaskForceStatus,
    WeaponReleaseAuthority,
)

GeoPoint = list[float]  # [lon, lat]
GameTick = int


# ---------------------------------------------------------------------------
# Weapon / Loadout
# ---------------------------------------------------------------------------


class WeaponStation(BaseModel):
    station_id: str
    weapon_type_key: str
    quantity: int
    quantity_max: int


class AmmoLoadout(BaseModel):
    stations: list[WeaponStation] = Field(default_factory=list)

    def total_rounds(self) -> int:
        return sum(s.quantity for s in self.stations)


# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------


class SensorSuiteTemplate(BaseModel):
    radar_range_km: float = 0.0
    radar_cross_section_modifier: float = 1.0  # multiplier on detectability
    ew_capability: bool = False
    sonar_range_km: float = 0.0
    ir_range_km: float = 0.0
    sigint_capability: bool = False


class SensorSuite(SensorSuiteTemplate):
    degradation: float = 0.0  # 0.0 = fully operational


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------


class SignatureProfile(BaseModel):
    radar_cross_section_m2: float = 10.0
    ir_signature: float = 1.0  # relative scale
    acoustic_signature: float = 1.0
    visual_signature: float = 1.0


# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------


class ResourceCost(BaseModel):
    budget_billions: float = 0.0
    steel_tons: float = 0.0
    rare_earths_tons: float = 0.0
    electronics_units: float = 0.0
    labor_hours: float = 0.0


class MunitionsInventory(BaseModel):
    tomahawk: int = 0
    harpoon: int = 0
    aim120_amraam: int = 0
    aim9x_sidewinder: int = 0
    aim174b: int = 0
    agm88_harm: int = 0
    agm154_jsow: int = 0
    agm158_jassm: int = 0
    agm158c_lrasm: int = 0
    mk48_torpedo: int = 0
    mk54_torpedo: int = 0
    sm2: int = 0
    sm3: int = 0
    sm6: int = 0
    thaad_interceptor: int = 0
    pac3_interceptor: int = 0
    artillery_155mm: int = 0
    gbu12_paveway: int = 0
    gbu31_jdam: int = 0
    gbu39_sdb: int = 0
    mk82_bomb: int = 0
    mk84_bomb: int = 0


class ResourceState(BaseModel):
    faction: Faction
    tick: GameTick = 0
    budget_billions: float = 850.0
    budget_burn_rate_per_tick: float = 0.097  # ~$850B / 8760 ticks/year
    steel_tons: float = 5_000_000.0
    rare_earths_tons: float = 50_000.0
    electronics_units: float = 1_000_000.0
    labor_capacity: float = 1_000_000.0
    fuel_reserves_barrels: float = 700_000_000.0
    munitions_stockpile: MunitionsInventory = Field(default_factory=MunitionsInventory)
    supply_chain_disruption: float = 0.0  # 0.0–1.0


# ---------------------------------------------------------------------------
# PlatformType (template / definition)
# ---------------------------------------------------------------------------


class Hardpoint(BaseModel):
    station_id: str
    compatible_weapons: list[str]
    max_quantity: int


class PlatformType(BaseModel):
    type_key: str
    display_name: str
    category: PlatformClass
    faction: Faction
    max_speed_knots: float
    cruise_speed_knots: float
    max_range_nm: float
    fuel_capacity_lbs: float
    fuel_burn_rate_per_tick: float  # lbs per tick at cruise speed
    crew_requirement: int
    hardpoints: list[Hardpoint] = Field(default_factory=list)
    sensor_suite: SensorSuiteTemplate = Field(default_factory=SensorSuiteTemplate)
    signature: SignatureProfile = Field(default_factory=SignatureProfile)
    build_cost: ResourceCost = Field(default_factory=ResourceCost)
    build_time_ticks: int = 0
    maintenance_interval_ticks: int = 720  # 30 days
    upgrade_paths: list[str] = Field(default_factory=list)
    description: str = ""
    service: str = ""  # USN, USAF, USA, USMC, USSF


# ---------------------------------------------------------------------------
# Platform (live entity)
# ---------------------------------------------------------------------------


class Platform(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    designation: str
    platform_class: PlatformClass
    type_key: str
    faction: Faction
    status: PlatformStatus = PlatformStatus.ACTIVE
    position: GeoPoint | None = None
    heading: float | None = None       # degrees true
    speed: float | None = None         # knots
    altitude: float | None = None      # feet MSL
    fuel_state: float = 1.0            # 0.0–1.0
    ammo_state: AmmoLoadout = Field(default_factory=AmmoLoadout)
    maintenance_due_tick: GameTick = 720
    assigned_mission_id: UUID | None = None
    assigned_tf_id: UUID | None = None
    parent_platform_id: UUID | None = None
    sensor_suite: SensorSuite = Field(default_factory=SensorSuite)
    health: float = 1.0                # 0.0–1.0
    created_tick: GameTick = 0
    destroyed_tick: GameTick | None = None


# ---------------------------------------------------------------------------
# Task Force
# ---------------------------------------------------------------------------


class FormationProfile(BaseModel):
    type: str = "STANDARD"  # STANDARD | DISPERSED | TIGHT | COLUMN
    spacing_nm: float = 2.0


class TaskForce(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    commander_unit_id: UUID
    assigned_unit_ids: list[UUID] = Field(default_factory=list)
    mission_id: UUID | None = None
    formation: FormationProfile = Field(default_factory=FormationProfile)
    status: TaskForceStatus = TaskForceStatus.ASSEMBLING
    logistics_node_id: UUID | None = None


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------


class ROEProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = "DEFAULT"
    fire_first: bool = False
    engagement_range_km: float = 50.0
    collateral_damage_threshold: float = 0.5  # 0.0 = zero tolerance
    target_priorities: list[str] = Field(default_factory=list)
    weapon_release_authority: WeaponReleaseAuthority = WeaponReleaseAuthority.COMMANDER
    nuclear_release_authorized: bool = False


class Waypoint(BaseModel):
    sequence: int
    position: GeoPoint
    action: str = "TRANSIT"  # TRANSIT | HOLD | STRIKE | RECON | RTB
    hold_ticks: int = 0
    altitude_ft: float | None = None
    speed_knots: float | None = None


class MissionTarget(BaseModel):
    target_type: str  # POINT | PLATFORM | AREA
    position: GeoPoint | None = None
    platform_id: UUID | None = None
    area_polygon: list[GeoPoint] | None = None
    description: str = ""


class MissionEvent(BaseModel):
    tick: GameTick
    event_type: str
    narrative: str
    data: dict[str, Any] = Field(default_factory=dict)


class Mission(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    type: MissionType
    status: MissionStatus = MissionStatus.PLANNED
    assigned_tf_id: UUID
    target: MissionTarget
    roe: ROEProfile = Field(default_factory=ROEProfile)
    start_tick: GameTick = 0
    end_tick: GameTick | None = None
    waypoints: list[Waypoint] = Field(default_factory=list)
    priority: int = 5  # 1–10
    commander_notes: str = ""
    events: list[MissionEvent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Facility
# ---------------------------------------------------------------------------


class ProductionOrder(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    facility_id: UUID
    platform_type_key: str
    quantity: int
    quantity_complete: int = 0
    ticks_per_unit: int
    ticks_elapsed: int = 0
    priority: int = 5
    resource_reserved: ResourceCost = Field(default_factory=ResourceCost)
    surge_mode: bool = False


class StorageState(BaseModel):
    fuel_barrels: float = 0.0
    munitions: MunitionsInventory = Field(default_factory=MunitionsInventory)
    spare_parts_units: int = 0


class Facility(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: FacilityType
    name: str
    faction: Faction
    position: GeoPoint
    production_slots: int = 1
    production_queue: list[ProductionOrder] = Field(default_factory=list)
    storage: StorageState = Field(default_factory=StorageState)
    health: float = 1.0
    workforce: int = 0
    power_state: PowerState = PowerState.OPERATIONAL


# ---------------------------------------------------------------------------
# Intelligence
# ---------------------------------------------------------------------------


class IntelligenceTrack(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    faction_observer: Faction
    target_platform_id: UUID | None = None
    track_type: IntelTrackType = IntelTrackType.POSSIBLE
    last_position: GeoPoint
    last_updated_tick: GameTick
    estimated_heading: float | None = None
    estimated_speed: float | None = None
    platform_type_estimate: str | None = None
    confidence: float = 0.5  # 0.0–1.0
    source: IntelSource


# ---------------------------------------------------------------------------
# Combat Event (immutable log)
# ---------------------------------------------------------------------------


class CombatEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tick: GameTick
    event_type: CombatEventType
    initiator_id: UUID
    target_id: UUID
    weapon_type_key: str | None = None
    position: GeoPoint
    probability_used: float
    roll_result: float
    outcome: str
    damage_applied: float | None = None
    narrative: str


# ---------------------------------------------------------------------------
# Game State (top-level snapshot)
# ---------------------------------------------------------------------------


class GameState(BaseModel):
    game_id: UUID = Field(default_factory=uuid4)
    scenario_id: str
    current_tick: GameTick = 0
    paused: bool = True
    tick_speed_multiplier: float = 1.0  # 1x = real-time, 10x = 10x speed
    platforms: dict[str, Platform] = Field(default_factory=dict)
    task_forces: dict[str, TaskForce] = Field(default_factory=dict)
    missions: dict[str, Mission] = Field(default_factory=dict)
    facilities: dict[str, Facility] = Field(default_factory=dict)
    intel_tracks: dict[str, IntelligenceTrack] = Field(default_factory=dict)
    combat_events: list[CombatEvent] = Field(default_factory=list)
    resource_states: dict[str, ResourceState] = Field(default_factory=dict)
