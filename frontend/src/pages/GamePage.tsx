import { useEffect } from "react";
import { useParams, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { connectToGame } from "@/lib/socket";
import { useGameStore } from "@/store/gameStore";
import { TopBar } from "@/components/layout/TopBar";
import { SideNav } from "@/components/layout/SideNav";
import { TheaterMap } from "@/components/map/TheaterMap";
import { ForceStructurePanel } from "@/components/panels/ForceStructurePanel";
import { MissionsPanel } from "@/components/panels/MissionsPanel";
import { DIBPanel } from "@/components/panels/DIBPanel";
import { IntelPanel } from "@/components/panels/IntelPanel";
import { AlertFeed } from "@/components/panels/AlertFeed";
import { GameOverlay } from "@/components/GameOverlay";
import { LogisticsPanel } from "@/components/panels/LogisticsPanel";
import { CombatLogPanel } from "@/components/panels/CombatLogPanel";
import { ObjectivesPanel } from "@/components/panels/ObjectivesPanel";
import type { GameSession, Platform, Mission, TaskForce, Facility, IntelTrack } from "@/types";

const PANEL_MAP = {
  force:      <ForceStructurePanel />,
  missions:   <MissionsPanel />,
  combat:     <CombatLogPanel />,
  dib:        <DIBPanel />,
  intel:      <IntelPanel />,
  logistics:  <LogisticsPanel />,
  objectives: <ObjectivesPanel />,
};

export function GamePage() {
  const { gameId } = useParams<{ gameId: string }>();
  const {
    setActiveGame,
    setPlatforms, setMissions, setTaskForces, setFacilities, setIntelTracks,
    activePanel,
  } = useGameStore();

  const { data: game, isError } = useQuery<GameSession>({
    queryKey: ["game", gameId],
    queryFn: () => api.getGame(gameId!) as Promise<GameSession>,
    enabled: !!gameId,
  });

  // Load all entity collections
  useQuery({
    queryKey: ["platforms", gameId],
    queryFn: async () => {
      const data = await api.listPlatforms(gameId!) as Platform[];
      setPlatforms(data);
      return data;
    },
    enabled: !!gameId,
    refetchInterval: 5000,
  });

  useQuery({
    queryKey: ["missions", gameId],
    queryFn: async () => {
      const data = await api.listMissions(gameId!) as Mission[];
      setMissions(data);
      return data;
    },
    enabled: !!gameId,
    refetchInterval: 10000,
  });

  useQuery({
    queryKey: ["taskForces", gameId],
    queryFn: async () => {
      const data = await api.listTaskForces(gameId!) as TaskForce[];
      setTaskForces(data);
      return data;
    },
    enabled: !!gameId,
    refetchInterval: 10000,
  });

  useQuery({
    queryKey: ["facilities", gameId],
    queryFn: async () => {
      const data = await api.listFacilities(gameId!) as Facility[];
      setFacilities(data);
      return data;
    },
    enabled: !!gameId,
    refetchInterval: 15000,
  });

  useQuery({
    queryKey: ["intel", gameId],
    queryFn: async () => {
      const data = await api.listTracks(gameId!) as IntelTrack[];
      setIntelTracks(data);
      return data;
    },
    enabled: !!gameId,
    refetchInterval: 8000,
  });

  useEffect(() => {
    if (game) {
      setActiveGame(game);
      connectToGame(game.id);
    }
  }, [game, setActiveGame]);

  if (isError) return <Navigate to="/" />;

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-surface-950">
      <TopBar />

      <div className="flex flex-1 overflow-hidden">
        <SideNav />

        {/* Left panel */}
        {activePanel && (
          <div className="w-72 shrink-0 panel border-r border-surface-700 overflow-hidden flex flex-col bg-surface-900">
            {PANEL_MAP[activePanel]}
          </div>
        )}

        {/* Map */}
        <div className="flex-1 relative overflow-hidden">
          <TheaterMap />
          <AlertFeed />
          <GameOverlay />
        </div>

        {/* Right info rail — always visible */}
        <div className="w-48 shrink-0 bg-surface-900 border-l border-surface-700 flex flex-col overflow-hidden">
          <ReadinessRail />
        </div>
      </div>
    </div>
  );
}

function ReadinessRail() {
  const { platforms, missions, activeGame } = useGameStore();

  const usPlatforms = Object.values(platforms).filter((p) => p.faction === "US");
  const planPlatforms = Object.values(platforms).filter((p) => p.faction !== "US" && p.status !== "DESTROYED");
  const activeMissions = Object.values(missions).filter((m) => m.status === "ACTIVE").length;
  const avgHealth = usPlatforms.length > 0
    ? usPlatforms.reduce((s, p) => s + p.health, 0) / usPlatforms.length
    : 0;
  const avgFuel = usPlatforms.length > 0
    ? usPlatforms.reduce((s, p) => s + p.fuel_state, 0) / usPlatforms.length
    : 0;

  const healthColor = avgHealth > 0.7 ? "text-accent-green" : avgHealth > 0.4 ? "text-accent-amber" : "text-accent-red";
  const fuelColor = avgFuel > 0.5 ? "text-accent-green" : avgFuel > 0.25 ? "text-accent-amber" : "text-accent-red";

  return (
    <>
      <div className="panel-header">
        <span className="panel-title">Readiness</span>
      </div>
      <div className="p-3 space-y-3">
        <StatBlock label="TICK" value={`T+${activeGame?.current_tick ?? 0}`} color="text-surface-100" />
        <StatBlock label="US UNITS" value={usPlatforms.length} color="text-surface-100" />
        <StatBlock label="PLAN UNITS" value={planPlatforms.length} color="text-accent-red" />
        <StatBlock label="ACTIVE MSNS" value={activeMissions} color="text-accent-blue" />
        <StatBlock label="AVG HEALTH" value={`${Math.round(avgHealth * 100)}%`} color={healthColor} />
        <StatBlock label="AVG FUEL" value={`${Math.round(avgFuel * 100)}%`} color={fuelColor} />
      </div>

      <div className="border-t border-surface-700 p-3 mt-auto">
        <div className="text-2xs font-mono text-surface-500 uppercase tracking-wider mb-2">SITREP</div>
        {activeMissions === 0 ? (
          <p className="text-2xs font-mono text-surface-500">No active missions</p>
        ) : (
          <p className="text-2xs font-mono text-surface-200">{activeMissions} mission{activeMissions > 1 ? "s" : ""} in progress</p>
        )}
      </div>
    </>
  );
}

function StatBlock({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className={`stat-value text-lg ${color}`}>{value}</div>
    </div>
  );
}
