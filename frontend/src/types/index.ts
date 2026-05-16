export type GeoPoint = [number, number]; // [lon, lat]
export type GameTick = number;

export type Faction = "US" | "ADVERSARY_A" | "ADVERSARY_B" | "NEUTRAL";
export type PlatformClass = "SHIP" | "AIRCRAFT" | "MISSILE" | "SATELLITE" | "VEHICLE" | "FACILITY" | "SUBMARINE" | "UAV";
export type PlatformStatus = "ACTIVE" | "DESTROYED" | "IN_TRANSIT" | "UNDER_MAINTENANCE" | "IN_PRODUCTION" | "DOCKED" | "AIRBORNE" | "SUBMERGED" | "RETIRED";
export type MissionType = "STRIKE" | "PATROL" | "INTERCEPT" | "RECON" | "ESCORT" | "SEAD" | "CAS" | "ASW" | "AAW" | "ASUW" | "LOGISTICS" | "ISR" | "EW";
export type MissionStatus = "PLANNED" | "ACTIVE" | "COMPLETE" | "ABORTED" | "FAILED" | "SUSPENDED";
export type TaskForceStatus = "ASSEMBLING" | "READY" | "UNDERWAY" | "ENGAGED" | "DISPERSED" | "RETURNED";

export interface Platform {
  id: string;
  designation: string;
  platform_class: PlatformClass;
  type_key: string;
  faction: Faction;
  status: PlatformStatus;
  position: GeoPoint | null;
  heading: number | null;
  speed: number | null;
  altitude: number | null;
  fuel_state: number;
  health: number;
  maintenance_due_tick: number;
  assigned_mission_id: string | null;
  assigned_tf_id: string | null;
  ammo_state: Record<string, unknown>;
  created_tick: number;
  destroyed_tick: number | null;
}

export interface PlatformType {
  type_key: string;
  display_name: string;
  category: PlatformClass;
  faction: Faction;
  service: string;
  max_speed_knots: number;
  cruise_speed_knots: number;
  max_range_nm: number;
  crew_requirement: number;
  build_time_ticks: number;
  build_cost: Record<string, number>;
  hardpoints: Array<{
    station_id: string;
    compatible_weapons: string[];
    max_quantity: number;
  }>;
  sensor_suite: Record<string, unknown>;
  signature: Record<string, unknown>;
  description: string;
}

export interface TaskForce {
  id: string;
  name: string;
  commander_unit_id: string;
  assigned_unit_ids: string[];
  mission_id: string | null;
  formation: Record<string, unknown>;
  status: TaskForceStatus;
  logistics_node_id: string | null;
}

export interface Mission {
  id: string;
  name: string;
  mission_type: MissionType;
  status: MissionStatus;
  assigned_tf_id: string;
  target: Record<string, unknown>;
  roe: Record<string, unknown>;
  start_tick: number;
  end_tick: number | null;
  waypoints: unknown[];
  priority: number;
  commander_notes: string;
  events: unknown[];
}

export interface Facility {
  id: string;
  facility_type: string;
  name: string;
  faction: Faction;
  position: GeoPoint;
  production_slots: number;
  health: number;
  workforce: number;
  power_state: string;
  production_queue: unknown[];
  storage: Record<string, unknown>;
}

export interface GameSession {
  id: string;
  scenario_id: string;
  current_tick: number;
  paused: boolean;
  tick_speed_multiplier: number;
}

export interface IntelTrack {
  id: string;
  faction_observer: Faction;
  target_platform_id: string | null;
  track_type: "CONFIRMED" | "PROBABLE" | "POSSIBLE" | "GHOST";
  last_position: GeoPoint;
  last_updated_tick: number;
  estimated_heading: number | null;
  estimated_speed: number | null;
  platform_type_estimate: string | null;
  confidence: number;
  source: string;
}

// ── Phase 2 types ──────────────────────────────────────────────────────────

export interface PlatformDelta {
  id: string;
  position?: [number, number] | null;
  heading?: number | null;
  speed?: number | null;
  fuel_state?: number | null;
  health?: number | null;
  status?: PlatformStatus | null;
}

export interface CombatEvent {
  tick: number;
  attacker_id: string;
  target_id: string;
  attacker_faction: string;
  weapon_type: string;
  distance_nm: number;
  hit: boolean;
  damage: number;
  target_health_after: number;
  narrative: string;
}

export interface IntelUpdate {
  id: string;
  target_platform_id?: string | null;
  faction_observer: string;
  track_type: "CONFIRMED" | "PROBABLE" | "POSSIBLE" | "GHOST";
  position: [number, number];
  estimated_heading: number | null;
  estimated_speed: number | null;
  platform_type_estimate: string | null;
  confidence: number;
  source: string;
  last_updated_tick: number;
}

export interface GameOverData {
  winner: "US" | "ADVERSARY" | "DRAW";
  reason: string;
  tick: number;
  us_losses: number;
  plan_losses: number;
}

// ── Phase 8: Scenario events + objectives ─────────────────────────────────

export type ScenarioEventType = "INTEL" | "ALERT" | "DIPLOMATIC" | "COMBAT" | "SYSTEM";

export interface ScenarioEvent {
  id: string;
  tick: number;
  type: ScenarioEventType;
  classification: string;
  title: string;
  body: string;
  source: string;
}

export type ObjectiveStatus = "PENDING" | "ACTIVE" | "COMPLETE" | "FAILED";
export type ObjectiveType = "STRATEGIC" | "OPERATIONAL" | "DEFENSIVE" | "TACTICAL";

export interface ScenarioObjective {
  id: string;
  title: string;
  description: string;
  type: ObjectiveType;
  status: ObjectiveStatus;
  progress: number;
  detail: string;
}
