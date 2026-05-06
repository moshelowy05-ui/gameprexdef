import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import type { GameSession, Platform, Mission, TaskForce, Facility, IntelTrack, PlatformDelta, CombatEvent, IntelUpdate, GameOverData, ScenarioEvent, ScenarioObjective } from "@/types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type S = any;

interface GameStore {
  // Active session
  activeGame: GameSession | null;
  setActiveGame: (game: GameSession | null) => void;
  updateTick: (tick: number, paused: boolean) => void;

  // Entity collections
  platforms: Record<string, Platform>;
  missions: Record<string, Mission>;
  taskForces: Record<string, TaskForce>;
  facilities: Record<string, Facility>;
  intelTracks: Record<string, IntelTrack>;

  setPlatforms: (platforms: Platform[]) => void;
  updatePlatform: (platform: Platform) => void;
  setMissions: (missions: Mission[]) => void;
  setTaskForces: (tfs: TaskForce[]) => void;
  setFacilities: (facilities: Facility[]) => void;
  setIntelTracks: (tracks: IntelTrack[]) => void;

  // UI state
  selectedPlatformId: string | null;
  selectedMissionId: string | null;
  selectedTfId: string | null;
  activePanel: "force" | "missions" | "dib" | "intel" | "logistics" | "combat" | "objectives" | null;

  selectPlatform: (id: string | null) => void;
  selectMission: (id: string | null) => void;
  selectTaskForce: (id: string | null) => void;
  setActivePanel: (panel: GameStore["activePanel"]) => void;

  // Alert queue
  alerts: Alert[];
  pushAlert: (alert: Omit<Alert, "id" | "timestamp">) => void;
  dismissAlert: (id: string) => void;

  // Phase 2 state
  combatEvents: CombatEvent[];
  gameOver: GameOverData | null;

  applyPlatformDeltas: (deltas: PlatformDelta[]) => void;
  addCombatEvents: (events: CombatEvent[]) => void;
  updateIntelTracks: (updates: IntelUpdate[]) => void;
  setGameOver: (data: GameOverData) => void;
  applyMissionUpdates: (updates: Array<{ id: string; status: string; [key: string]: unknown }>) => void;

  // Phase 8: scenario events + objectives + waypoints
  scenarioEvents: ScenarioEvent[];
  pushScenarioEvent: (event: ScenarioEvent) => void;
  objectives: ScenarioObjective[];
  setObjectives: (objectives: ScenarioObjective[]) => void;
  // pending waypoints: platformId → destination [lon, lat] (cleared on arrival)
  pendingWaypoints: Record<string, [number, number]>;
  setPendingWaypoint: (platformId: string, destination: [number, number] | null) => void;

  // Order mode — MOVE_TO: waypoint selection; ATTACK: click enemy to move towards it; PICK_TARGET: mission target pick
  orderMode: { active: boolean; platformId: string | null; orderType: "MOVE_TO" | "ATTACK" | "PICK_TARGET" | null };
  setOrderMode: (mode: GameStore["orderMode"]) => void;
  clearOrderMode: () => void;
  // callback invoked when PICK_TARGET click resolves
  pickTargetCallback: ((lon: number, lat: number) => void) | null;
  setPickTargetCallback: (cb: ((lon: number, lat: number) => void) | null) => void;

  // Speed — optimistic local update
  updateSpeed: (multiplier: number) => void;
}

interface Alert {
  id: string;
  level: "info" | "warning" | "critical";
  title: string;
  body: string;
  timestamp: number;
}

let alertCounter = 0;

export const useGameStore = create<GameStore>()(
  immer((set) => ({
    activeGame: null,
    setActiveGame: (game: GameSession | null) =>
      set((s: S) => {
        s.activeGame = game;
      }),
    updateTick: (tick: number, paused: boolean) =>
      set((s: S) => {
        if (s.activeGame) {
          s.activeGame.current_tick = tick;
          s.activeGame.paused = paused;
        }
      }),

    platforms: {},
    missions: {},
    taskForces: {},
    facilities: {},
    intelTracks: {},

    setPlatforms: (platforms: Platform[]) =>
      set((s: S) => {
        s.platforms = Object.fromEntries(platforms.map((p) => [p.id, p]));
      }),
    updatePlatform: (platform: Platform) =>
      set((s: S) => {
        s.platforms[platform.id] = platform;
      }),
    setMissions: (missions: Mission[]) =>
      set((s: S) => {
        s.missions = Object.fromEntries(missions.map((m) => [m.id, m]));
      }),
    setTaskForces: (tfs: TaskForce[]) =>
      set((s: S) => {
        s.taskForces = Object.fromEntries(tfs.map((t) => [t.id, t]));
      }),
    setFacilities: (facilities: Facility[]) =>
      set((s: S) => {
        s.facilities = Object.fromEntries(facilities.map((f) => [f.id, f]));
      }),
    setIntelTracks: (tracks: IntelTrack[]) =>
      set((s: S) => {
        s.intelTracks = Object.fromEntries(tracks.map((t) => [t.id, t]));
      }),

    selectedPlatformId: null,
    selectedMissionId: null,
    selectedTfId: null,
    activePanel: "force",

    selectPlatform: (id: string | null) =>
      set((s: S) => {
        s.selectedPlatformId = id;
      }),
    selectMission: (id: string | null) =>
      set((s: S) => {
        s.selectedMissionId = id;
      }),
    selectTaskForce: (id: string | null) =>
      set((s: S) => {
        s.selectedTfId = id;
      }),
    setActivePanel: (panel: GameStore["activePanel"]) =>
      set((s: S) => {
        s.activePanel = panel;
      }),

    alerts: [],
    pushAlert: (alert: Omit<Alert, "id" | "timestamp">) =>
      set((s: S) => {
        s.alerts.unshift({
          ...alert,
          id: String(++alertCounter),
          timestamp: Date.now(),
        });
        if (s.alerts.length > 50) s.alerts.length = 50;
      }),
    dismissAlert: (id: string) =>
      set((s: S) => {
        s.alerts = s.alerts.filter((a: Alert) => a.id !== id);
      }),

    combatEvents: [],
    gameOver: null,

    applyPlatformDeltas: (deltas: PlatformDelta[]) =>
      set((s: S) => {
        for (const delta of deltas) {
          const p = s.platforms[delta.id];
          if (!p) continue;
          if (delta.position != null) p.position = delta.position;
          if (delta.heading != null) p.heading = delta.heading;
          if (delta.speed != null) {
            p.speed = delta.speed;
            // Clear pending waypoint once platform stops (arrives at destination)
            if (delta.speed === 0 && s.pendingWaypoints[delta.id]) {
              delete s.pendingWaypoints[delta.id];
            }
          }
          if (delta.fuel_state != null) p.fuel_state = delta.fuel_state;
          if (delta.health != null) p.health = delta.health;
          if (delta.status != null) p.status = delta.status;
        }
      }),

    addCombatEvents: (events: CombatEvent[]) =>
      set((s: S) => {
        s.combatEvents.push(...events);
        if (s.combatEvents.length > 300) {
          s.combatEvents = s.combatEvents.slice(-300);
        }
      }),

    updateIntelTracks: (updates: IntelUpdate[]) =>
      set((s: S) => {
        for (const track of updates) {
          s.intelTracks[track.id] = {
            id: track.id,
            faction_observer: track.faction_observer as any,
            target_platform_id: null,
            track_type: track.track_type,
            last_position: track.position,
            last_updated_tick: track.last_updated_tick,
            estimated_heading: track.estimated_heading,
            estimated_speed: track.estimated_speed,
            platform_type_estimate: track.platform_type_estimate,
            confidence: track.confidence,
            source: track.source,
          };
        }
      }),

    setGameOver: (data: GameOverData) =>
      set((s: S) => {
        s.gameOver = data;
        s.activeGame && (s.activeGame.paused = true);
      }),

    applyMissionUpdates: (updates: Array<{ id: string; status: string; [key: string]: unknown }>) =>
      set((s: S) => {
        updates.forEach((u: { id: string; status: string; [key: string]: unknown }) => {
          if (s.missions[u.id]) {
            s.missions[u.id] = { ...s.missions[u.id], ...u } as Mission;
          }
        });
      }),

    orderMode: { active: false, platformId: null, orderType: null },
    setOrderMode: (mode: GameStore["orderMode"]) => set((s: S) => { s.orderMode = mode; }),
    clearOrderMode: () => set((s: S) => {
      s.orderMode = { active: false, platformId: null, orderType: null };
      s.pickTargetCallback = null;
    }),
    pickTargetCallback: null,
    setPickTargetCallback: (cb: ((lon: number, lat: number) => void) | null) =>
      set((s: S) => { s.pickTargetCallback = cb; }),
    updateSpeed: (multiplier: number) => set((s: S) => {
      if (s.activeGame) s.activeGame.tick_speed_multiplier = multiplier;
    }),

    scenarioEvents: [],
    pushScenarioEvent: (event: ScenarioEvent) =>
      set((s: S) => {
        s.scenarioEvents.unshift(event);
        if (s.scenarioEvents.length > 100) s.scenarioEvents.length = 100;
      }),

    objectives: [],
    setObjectives: (objectives: ScenarioObjective[]) =>
      set((s: S) => { s.objectives = objectives; }),

    pendingWaypoints: {},
    setPendingWaypoint: (platformId: string, destination: [number, number] | null) =>
      set((s: S) => {
        if (destination === null) {
          delete s.pendingWaypoints[platformId];
        } else {
          s.pendingWaypoints[platformId] = destination;
        }
      }),
  }))
);
