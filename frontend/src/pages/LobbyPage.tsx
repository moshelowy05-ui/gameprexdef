import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Shield, Plus, Play, Clock } from "lucide-react";
import type { GameSession } from "@/types";

const SCENARIOS = [
  { id: "taiwan_strait_2026",    name: "Taiwan Strait Crisis",          description: "Cross-strait amphibious assault. Pacific deterrence." },
  { id: "arctic_confrontation",  name: "Arctic Confrontation",          description: "Northern sea route dispute. High-latitude naval ops." },
  { id: "persian_gulf_closure",  name: "Persian Gulf Closure",          description: "Strait of Hormuz blockade. Energy security crisis." },
  { id: "korean_peninsula",      name: "Korean Peninsula Contingency",  description: "Armistice collapse. Combined forces response." },
];

export function LobbyPage() {
  const navigate = useNavigate();
  const [selectedScenario, setSelectedScenario] = useState(SCENARIOS[0].id);
  const [creating, setCreating] = useState(false);

  const { data: games, refetch } = useQuery<GameSession[]>({
    queryKey: ["games"],
    queryFn: () => api.listGames() as Promise<GameSession[]>,
  });

  const handleCreate = async () => {
    setCreating(true);
    try {
      const game = await api.createGame(selectedScenario) as GameSession;
      navigate(`/game/${game.id}`);
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-950 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <Shield className="w-6 h-6 text-accent-blue" />
          <div>
            <h1 className="text-lg font-mono font-semibold text-surface-100 tracking-wider">
              COMMAND CENTER
            </h1>
            <p className="text-xs font-mono text-surface-400">Select scenario or resume campaign</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* New game */}
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">New Campaign</span>
            </div>
            <div className="p-4 space-y-3">
              {SCENARIOS.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedScenario(s.id)}
                  className={`w-full text-left p-3 rounded border transition-colors ${
                    selectedScenario === s.id
                      ? "bg-accent-blue/10 border-accent-blue/40 "
                      : "bg-surface-800 border-surface-700 hover:border-surface-500"
                  }`}
                >
                  <div className="text-sm font-mono font-medium text-surface-100">{s.name}</div>
                  <div className="text-2xs font-mono text-surface-400 mt-0.5">{s.description}</div>
                </button>
              ))}
              <button
                onClick={handleCreate}
                disabled={creating}
                className="w-full btn-primary py-2.5 justify-center mt-4"
              >
                <Plus className="w-4 h-4" />
                {creating ? "Initializing..." : "Launch Campaign"}
              </button>
            </div>
          </div>

          {/* Existing games */}
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Active Campaigns</span>
              <span className="text-2xs font-mono text-surface-400">{games?.length ?? 0} saved</span>
            </div>
            <div className="divide-y divide-surface-800">
              {!games?.length && (
                <div className="p-6 text-center text-surface-500 text-xs font-mono">
                  No saved campaigns
                </div>
              )}
              {games?.map((g) => (
                <button
                  key={g.id}
                  onClick={() => navigate(`/game/${g.id}`)}
                  className="w-full text-left px-4 py-3 hover:bg-surface-800 transition-colors flex items-center gap-3"
                >
                  <Play className="w-4 h-4 text-accent-green shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-mono text-surface-100 uppercase">
                      {g.scenario_id.replace(/_/g, " ")}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <Clock className="w-3 h-3 text-surface-500" />
                      <span className="text-2xs font-mono text-surface-400">T+{g.current_tick}</span>
                      <span className={`text-2xs font-mono ${g.paused ? "text-accent-amber" : "text-accent-green"}`}>
                        {g.paused ? "PAUSED" : "RUNNING"}
                      </span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
