import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Shield, Plus, Play, Clock, ChevronDown } from "lucide-react";
import type { GameSession } from "@/types";

const SCENARIOS = [
  { id: "taiwan_strait_2026",    name: "Taiwan Strait Crisis",          description: "Cross-strait amphibious assault. Pacific deterrence." },
  { id: "arctic_confrontation",  name: "Arctic Confrontation",          description: "Northern sea route dispute. High-latitude naval ops." },
  { id: "persian_gulf_closure",  name: "Persian Gulf Closure",          description: "Strait of Hormuz blockade. Energy security crisis." },
  { id: "korean_peninsula",      name: "Korean Peninsula Contingency",  description: "Armistice collapse. Combined forces response." },
];

interface ScenarioDetail {
  classification: string;
  objectives: Array<{ id: string; title: string; description: string; type: string }>;
  victory_conditions: Record<string, string>;
  duration_ticks: number;
}

const SCENARIO_DETAILS: Record<string, ScenarioDetail> = {
  taiwan_strait_2026: {
    classification: "SECRET",
    objectives: [
      { id: "OBJ_01", title: "Establish Maritime Superiority", description: "Deploy CSGs to establish sea control in Philippine Sea and Taiwan Strait approaches.", type: "STRATEGIC" },
      { id: "OBJ_02", title: "Suppress PLAN Air Defense", description: "Conduct SEAD against PLA coastal SAM belts to enable air superiority.", type: "OPERATIONAL" },
      { id: "OBJ_03", title: "Break the Blockade", description: "Destroy or neutralize adversary naval forces enforcing the blockade.", type: "OPERATIONAL" },
    ],
    victory_conditions: {
      "US WIN": "Complete OBJ_01–03 within 720 ticks with <40% force attrition",
      "DRAW": "Ceasefire with Taiwan sovereignty intact, incomplete objectives",
      "DEFEAT": "Taiwan airbases destroyed or US carrier force >60% attrition",
    },
    duration_ticks: 720,
  },
  arctic_confrontation: {
    classification: "CONFIDENTIAL",
    objectives: [
      { id: "OBJ_01", title: "Secure Northern Sea Route", description: "Establish US/NATO naval presence in disputed Arctic waters.", type: "STRATEGIC" },
      { id: "OBJ_02", title: "Counter Russian Bastion", description: "Neutralize adversary submarine and surface threats in the Barents Sea.", type: "OPERATIONAL" },
    ],
    victory_conditions: {
      "US WIN": "Secure NSR transit rights, <30% attrition",
      "DRAW": "Negotiated access agreement",
      "DEFEAT": "Allied naval forces withdrawn from the Arctic",
    },
    duration_ticks: 480,
  },
};

const CLASSIFICATION_STYLE: Record<string, string> = {
  UNCLASSIFIED: "text-accent-green border-accent-green/40 bg-accent-green/10",
  CONFIDENTIAL: "text-accent-amber border-accent-amber/40 bg-accent-amber/10",
  SECRET:       "text-accent-red   border-accent-red/40   bg-accent-red/10",
};

const OBJECTIVE_TYPE_STYLE: Record<string, string> = {
  STRATEGIC:   "text-accent-red bg-accent-red/10",
  OPERATIONAL: "text-accent-amber bg-accent-amber/10",
  TACTICAL:    "text-accent-blue bg-accent-blue/10",
};

const VC_LABEL_STYLE: Record<string, string> = {
  "US WIN": "text-accent-green",
  "DRAW":   "text-accent-amber",
  "DEFEAT": "text-accent-red",
};

export function LobbyPage() {
  const navigate = useNavigate();
  const [selectedScenario, setSelectedScenario] = useState(SCENARIOS[0].id);
  const [expandedBriefId, setExpandedBriefId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const { data: games } = useQuery<GameSession[]>({
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

  const handleSelectScenario = (id: string) => {
    setSelectedScenario(id);
    // Toggle accordion: if already expanded for this scenario, collapse; else expand
    setExpandedBriefId((prev) => (prev === id ? null : id));
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
              {SCENARIOS.map((s) => {
                const details = SCENARIO_DETAILS[s.id];
                const isSelected = selectedScenario === s.id;
                const isBriefOpen = expandedBriefId === s.id;

                return (
                  <div key={s.id}>
                    <button
                      onClick={() => handleSelectScenario(s.id)}
                      className={`w-full text-left p-3 rounded border transition-colors ${
                        isSelected
                          ? "bg-accent-blue/10 border-accent-blue/40"
                          : "bg-surface-800 border-surface-700 hover:border-surface-500"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-mono font-medium text-surface-100">{s.name}</div>
                        {details && (
                          <ChevronDown
                            className={`w-3.5 h-3.5 text-surface-400 shrink-0 transition-transform ${
                              isBriefOpen ? "rotate-180" : ""
                            }`}
                          />
                        )}
                      </div>
                      <div className="text-2xs font-mono text-surface-400 mt-0.5">{s.description}</div>
                    </button>

                    {/* Accordion brief */}
                    {isSelected && isBriefOpen && details && (
                      <div className="border border-t-0 border-accent-blue/20 bg-surface-900 rounded-b p-3 space-y-3">
                        {/* Classification badge */}
                        <div>
                          <span
                            className={`inline-block px-2 py-0.5 text-2xs font-mono font-semibold uppercase tracking-widest border rounded ${
                              CLASSIFICATION_STYLE[details.classification] ?? "text-surface-400"
                            }`}
                          >
                            {details.classification}
                          </span>
                        </div>

                        {/* Objectives */}
                        <div>
                          <div className="text-2xs font-mono uppercase tracking-widest text-surface-500 mb-1.5">
                            Objectives
                          </div>
                          <div className="space-y-1.5">
                            {details.objectives.map((obj) => (
                              <div key={obj.id} className="flex gap-2 items-start">
                                <span
                                  className={`shrink-0 px-1 py-0.5 text-2xs font-mono uppercase rounded ${
                                    OBJECTIVE_TYPE_STYLE[obj.type] ?? "text-surface-400"
                                  }`}
                                >
                                  {obj.type}
                                </span>
                                <div>
                                  <div className="text-xs font-mono text-surface-200 font-medium">{obj.title}</div>
                                  <div className="text-2xs font-mono text-surface-400">{obj.description}</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Victory conditions */}
                        <div>
                          <div className="text-2xs font-mono uppercase tracking-widest text-surface-500 mb-1.5">
                            Victory Conditions
                          </div>
                          <div className="space-y-1">
                            {Object.entries(details.victory_conditions).map(([label, desc]) => (
                              <div key={label} className="flex gap-2 items-start">
                                <span
                                  className={`shrink-0 text-2xs font-mono font-semibold uppercase w-16 ${
                                    VC_LABEL_STYLE[label] ?? "text-surface-400"
                                  }`}
                                >
                                  {label}
                                </span>
                                <span className="text-2xs font-mono text-surface-300">{desc}</span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Duration */}
                        <div className="flex items-center gap-2">
                          <span className="text-2xs font-mono uppercase tracking-widest text-surface-500">Duration</span>
                          <span className="text-2xs font-mono text-surface-200">
                            {details.duration_ticks} ticks ({Math.round(details.duration_ticks / 24)} game-days)
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
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
