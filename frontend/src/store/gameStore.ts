import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import type { GameSession, Platform, Mission, TaskForce, Facility, IntelTrack, PlatformDelta, CombatEvent, IntelUpdate, GameOverData } from "@/types";

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
  activePanel: "force" | "missions" | "dib" | "intel" | "logistics" | "combat" | null;

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

  // Order mode — set when user activates "MOVE TO" waypoint selection
  orderMode: { active: boolean; platformId: string | null; orderType: "MOVE_TO" | null };
  setOrderMode: (mode: GameStore["orderMode"]) => void;
  clearOrderMode: () => void;

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
    setActiveGame: (game) =>
      set((s) => {
        s.activeGame = game;
      }),
    updateTick: (tick, paused) =>
      set((s) => {
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

    setPlatforms: (platforms) =>
      set((s) => {
        s.platforms = Object.fromEntries(platforms.map((p) => [p.id, p]));
      }),
    updatePlatform: (platform) =>
      set((s) => {
        s.platforms[platform.id] = platform;
      }),
    setMissions: (missions) =>
      set((s) => {
        s.missions = Object.fromEntries(missions.map((m) => [m.id, m]));
      }),
    setTaskForces: (tfs) =>
      set((s) => {
        s.taskForces = Object.fromEntries(tfs.map((t) => [t.id, t]));
      }),
    setFacilities: (facilities) =>
      set((s) => {
        s.facilities = Object.fromEntries(facilities.map((f) => [f.id, f]));
      }),
    setIntelTracks: (tracks) =>
      set((s) => {
        s.intelTracks = Object.fromEntries(tracks.map((t) => [t.id, t]));
      }),

    selectedPlatformId: null,
    selectedMissionId: null,
    selectedTfId: null,
    activePanel: "force",

    selectPlatform: (id) =>
      set((s) => {
        s.selectedPlatformId = id;
      }),
    selectMission: (id) =>
      set((s) => {
        s.selectedMissionId = id;
      }),
    selectTaskForce: (id) =>
      set((s) => {
        s.selectedTfId = id;
      }),
    setActivePanel: (panel) =>
      set((s) => {
        s.activePanel = panel;
      }),

    alerts: [],
    pushAlert: (alert) =>
      set((s) => {
        s.alerts.unshift({
          ...alert,
          id: String(++alertCounter),
          timestamp: Date.now(),
        });
        if (s.alerts.length > 50) s.alerts.length = 50;
      }),
    dismissAlert: (id) =>
      set((s) => {
        s.alerts = s.alerts.filter((a) => a.id !== id);
      }),

    combatEvents: [],
    gameOver: null,

    applyPlatformDeltas: (deltas) =>
      set((s) => {
        for (const delta of deltas) {
          const p = s.platforms[delta.id];
          if (!p) continue;
          if (delta.position != null) p.position = delta.position;
          if (delta.heading != null) p.heading = delta.heading;
          if (delta.speed != null) p.speed = delta.speed;
          if (delta.fuel_state != null) p.fuel_state = delta.fuel_state;
          if (delta.health != null) p.health = delta.health;
          if (delta.status != null) p.status = delta.status;
        }
      }),

    addCombatEvents: (events) =>
      set((s) => {
        s.combatEvents.push(...events);
        if (s.combatEvents.length > 300) {
          s.combatEvents = s.combatEvents.slice(-300);
        }
      }),

    updateIntelTracks: (updates) =>
      set((s) => {
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

    setGameOver: (data) =>
      set((s) => {
        s.gameOver = data;
        s.activeGame && (s.activeGame.paused = true);
      }),

    applyMissionUpdates: (updates) =>
      set((s) => {
        updates.forEach(u => {
          if (s.missions[u.id]) {
            s.missions[u.id] = { ...s.missions[u.id], ...u } as Mission;
          }
        });
      }),

    orderMode: { active: false, platformId: null, orderType: null },
    setOrderMode: (mode) => set((s) => { s.orderMode = mode; }),
    clearOrderMode: () => set((s) => { s.orderMode = { active: false, platformId: null, orderType: null }; }),
    updateSpeed: (multiplier) => set((s) => {
      if (s.activeGame) s.activeGame.tick_speed_multiplier = multiplier;
    }),
  }))
);
