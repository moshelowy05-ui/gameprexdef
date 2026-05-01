import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import type { GameSession, Platform, Mission, TaskForce, Facility, IntelTrack } from "@/types";

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
  activePanel: "force" | "missions" | "dib" | "intel" | "logistics" | null;

  selectPlatform: (id: string | null) => void;
  selectMission: (id: string | null) => void;
  selectTaskForce: (id: string | null) => void;
  setActivePanel: (panel: GameStore["activePanel"]) => void;

  // Alert queue
  alerts: Alert[];
  pushAlert: (alert: Omit<Alert, "id" | "timestamp">) => void;
  dismissAlert: (id: string) => void;
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
  }))
);
