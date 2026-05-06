import { useCallback, useEffect, useMemo, useState } from "react";
import Map, { NavigationControl, ScaleControl } from "react-map-gl/maplibre";
import { DeckGL } from "@deck.gl/react";
import { ScatterplotLayer, TextLayer, PathLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { useGameStore } from "@/store/gameStore";
import { api } from "@/lib/api";
import type { Platform, IntelTrack } from "@/types";
import { CommandBar } from "./CommandBar";
import "maplibre-gl/dist/maplibre-gl.css";

const MAP_STYLE = {
  version: 8 as const,
  sources: {
    "osm": {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{
    id: "osm",
    type: "raster" as const,
    source: "osm",
    paint: {
      "raster-brightness-min": 0.0,
      "raster-brightness-max": 0.15,
      "raster-saturation": -1.0,
      "raster-contrast": 0.2,
      "raster-hue-rotate": 200,
    },
  }],
};

// ── Colors ────────────────────────────────────────────────────────────────────

const C: Record<string, [number, number, number, number]> = {
  US_SHIP:      [45,  125, 210, 230],
  US_AIRCRAFT:  [20,  184, 212, 230],
  US_SUBMARINE: [139, 92,  246, 230],
  US_UAV:       [34,  197, 94,  220],
  US_VEHICLE:   [249, 115, 22,  220],
  ENEMY:        [239, 68,  68,  230],
  ENEMY_TARGET: [255, 50,  50,  255], // brighter when in attack mode
  INTEL:        [245, 158, 11,  200],
  SELECTED:     [255, 255, 255, 255],
};

function platformColor(p: Platform, attackMode: boolean): [number, number, number, number] {
  if (p.faction !== "US") return attackMode ? C.ENEMY_TARGET : C.ENEMY;
  const key = `US_${p.platform_class}`;
  return C[key] ?? C.US_SHIP;
}

function platformRadius(p: Platform): number {
  if (p.platform_class === "SHIP" || p.platform_class === "SUBMARINE") return 9000;
  if (p.platform_class === "AIRCRAFT" || p.platform_class === "UAV") return 6000;
  return 7000;
}

interface ViewState {
  longitude: number; latitude: number; zoom: number; pitch: number; bearing: number;
}

const DEFAULT_VIEW: ViewState = { longitude: 120, latitude: 20, zoom: 4, pitch: 0, bearing: 0 };

// ── Component ─────────────────────────────────────────────────────────────────

export function TheaterMap() {
  const {
    platforms, intelTracks,
    selectedPlatformId, selectPlatform,
    orderMode, clearOrderMode,
    activeGame,
    setPendingWaypoint, pendingWaypoints,
    pickTargetCallback,
    pushAlert,
  } = useGameStore();

  const [viewState, setViewState] = useState<ViewState>(DEFAULT_VIEW);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; object: Platform | IntelTrack } | null>(null);

  const attackMode = orderMode.active && orderMode.orderType === "ATTACK";

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") { clearOrderMode(); selectPlatform(null); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [clearOrderMode, selectPlatform]);

  // ── Map click handler ─────────────────────────────────────────────────────
  const handleMapClick = useCallback(
    async (info: PickingInfo) => {
      const gameId = activeGame?.id;

      // ── PICK_TARGET mode (mission form) ──────────────────────────────────
      if (orderMode.active && orderMode.orderType === "PICK_TARGET") {
        if (info.coordinate) {
          const [lon, lat] = info.coordinate as [number, number];
          pickTargetCallback?.(lon, lat);
        }
        clearOrderMode();
        return;
      }

      // ── ATTACK mode: click an enemy to move to intercept it ──────────────
      if (attackMode && orderMode.platformId) {
        const clicked = info.object as Platform | null;

        if (clicked && "id" in clicked && clicked.faction !== "US" && clicked.position) {
          // Move the attacker to the target's position with STRIKE action
          const [lon, lat] = clicked.position;
          if (gameId) {
            try {
              await api.submitOrder(gameId, orderMode.platformId, {
                order_type: "MOVE_TO",
                priority: 200,
                waypoints: [{ lon, lat, action: "STRIKE" }],
              });
              setPendingWaypoint(orderMode.platformId, [lon, lat]);
              const attacker = platforms[orderMode.platformId];
              pushAlert({
                level: "info",
                title: "Attack order sent",
                body: `${attacker?.designation ?? "Unit"} → intercepting ${clicked.designation}`,
              });
            } catch {
              pushAlert({ level: "warning", title: "Order failed", body: "Could not send attack order" });
            }
          }
        }
        // Any click (hit or miss) exits attack mode
        clearOrderMode();
        return;
      }

      // ── MOVE_TO mode: click empty ocean ───────────────────────────────────
      if (orderMode.active && orderMode.platformId && orderMode.orderType === "MOVE_TO") {
        // Only act on empty-map clicks (not on another unit)
        if (!info.object && info.coordinate) {
          const [lon, lat] = info.coordinate as [number, number];
          if (gameId) {
            try {
              await api.submitOrder(gameId, orderMode.platformId, {
                order_type: "MOVE_TO",
                priority: 200,
                waypoints: [{ lon, lat, action: "TRANSIT" }],
              });
              setPendingWaypoint(orderMode.platformId, [lon, lat]);
              const mover = platforms[orderMode.platformId];
              pushAlert({
                level: "info",
                title: "Move order sent",
                body: `${mover?.designation ?? "Unit"} → waypoint set`,
              });
            } catch {
              pushAlert({ level: "warning", title: "Order failed", body: "Could not send move order" });
            }
          }
          clearOrderMode();
          return;
        }
        // Clicked on a unit while in MOVE mode → select that unit instead
        if (info.object && "id" in info.object) {
          const p = info.object as Platform;
          clearOrderMode();
          selectPlatform(p.id);
          return;
        }
        clearOrderMode();
        return;
      }

      // ── Normal selection ──────────────────────────────────────────────────
      if (info.object && "id" in info.object) {
        selectPlatform((info.object as Platform).id);
      } else {
        selectPlatform(null);
      }
    },
    [orderMode, attackMode, activeGame, clearOrderMode, selectPlatform,
     setPendingWaypoint, pickTargetCallback, platforms, pushAlert],
  );

  // ── Deck.gl layers ────────────────────────────────────────────────────────

  const deployedPlatforms = useMemo(
    () => Object.values(platforms).filter((p) => p.position !== null && p.status !== "DESTROYED"),
    [platforms],
  );

  const activeTracks = useMemo(() => Object.values(intelTracks), [intelTracks]);

  const layers = useMemo(() => {
    // Pulse animation value using a sine wave — gives visual life to the map
    const now = Date.now();
    const pulse = 0.5 + 0.5 * Math.sin(now / 600);  // 0..1 at ~0.6Hz

    return [
      // Intel / unknown contacts — amber pulsing dots
      new ScatterplotLayer<IntelTrack>({
        id: "intel-tracks",
        data: activeTracks,
        getPosition: (d) => d.last_position,
        getRadius: 11000,
        getFillColor: (d) => [245, 158, 11, Math.round(d.confidence * 160)],
        getLineColor: [245, 158, 11, 100],
        stroked: true,
        lineWidthMinPixels: 1,
        pickable: true,
        onHover: (info: PickingInfo) => {
          if (info.object && info.x !== undefined) setTooltip({ x: info.x, y: info.y, object: info.object as IntelTrack });
          else setTooltip(null);
        },
      }),

      // ── Platform dots ────────────────────────────────────────────────────
      new ScatterplotLayer<Platform>({
        id: "platforms",
        data: deployedPlatforms,
        getPosition: (d) => d.position!,
        getRadius: (d) => {
          const base = platformRadius(d);
          // Enemy platforms pulse bigger in attack mode
          if (attackMode && d.faction !== "US") return base * (1 + pulse * 0.3);
          return base;
        },
        getFillColor: (d) => {
          if (d.id === selectedPlatformId) return C.SELECTED;
          return platformColor(d, attackMode);
        },
        getLineColor: (d) => {
          if (d.id === selectedPlatformId) return [45, 125, 210, 255];
          if (attackMode && d.faction !== "US") return [255, 60, 60, 255];
          return [255, 255, 255, 40];
        },
        lineWidthMinPixels: 1,
        stroked: true,
        pickable: true,
        onClick: (info: PickingInfo) => {
          if (info.object) {
            selectPlatform((info.object as Platform).id);
          }
          return true;  // consumed — prevents handleMapClick from also firing
        },
        onHover: (info: PickingInfo) => {
          if (info.object && info.x !== undefined) setTooltip({ x: info.x, y: info.y, object: info.object as Platform });
          else setTooltip(null);
        },
        updateTriggers: {
          getRadius: [attackMode, pulse],
          getFillColor: [selectedPlatformId, attackMode],
          getLineColor: [selectedPlatformId, attackMode],
        },
      }),

      // ── Selected unit ring ───────────────────────────────────────────────
      ...(selectedPlatformId && platforms[selectedPlatformId]?.position ? [
        new ScatterplotLayer({
          id: "selected-ring",
          data: [platforms[selectedPlatformId]],
          getPosition: (d: unknown) => (d as Platform).position!,
          getRadius: platformRadius(platforms[selectedPlatformId]) * 2.2,
          getFillColor: [0, 0, 0, 0],
          getLineColor: [45, 125, 210, 180],
          stroked: true,
          lineWidthMinPixels: 1.5,
          pickable: false,
        }),
      ] : []),

      // ── Pending waypoint paths ───────────────────────────────────────────
      new PathLayer({
        id: "waypoint-paths",
        data: Object.entries(pendingWaypoints).flatMap(([pid, dest]) => {
          const p = platforms[pid];
          if (!p?.position) return [];
          return [{ path: [p.position, dest] }];
        }),
        getPath: (d: unknown) => (d as { path: [number, number][] }).path,
        getColor: [45, 125, 210, 200],
        getWidth: 2,
        widthUnits: "pixels",
        getDashArray: [8, 5],
        dashJustified: true,
        extensions: [],
      }),

      // ── Friendly labels (close zoom only) ───────────────────────────────
      new TextLayer<Platform>({
        id: "platform-labels",
        data: deployedPlatforms.filter((p) => p.faction === "US"),
        getPosition: (d) => d.position!,
        getText: (d) => d.designation.split(" ").slice(0, 2).join(" "),
        getSize: 10,
        getColor: [160, 190, 220, 180],
        getPixelOffset: [0, -16],
        fontFamily: "JetBrains Mono, monospace",
        fontWeight: 500,
        visible: viewState.zoom > 6,
      }),
    ];
  }, [
    deployedPlatforms, activeTracks, selectedPlatformId,
    viewState.zoom, pendingWaypoints, platforms, attackMode, selectPlatform,
  ]);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="relative w-full h-full bg-surface-950">
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: vs }) => setViewState(vs as ViewState)}
        controller={true}
        layers={layers}
        style={{ position: "absolute", inset: "0" }}
        onClick={handleMapClick}
        getCursor={() => {
          if (attackMode) return "crosshair";
          if (orderMode.active) return "crosshair";
          return "auto";
        }}
      >
        <Map mapStyle={MAP_STYLE as never} style={{ width: "100%", height: "100%" }}>
          <NavigationControl position="bottom-right" />
          <ScaleControl position="bottom-left" unit="nautical" />
        </Map>
      </DeckGL>

      {/* Attack mode overlay banner — hard to miss */}
      {attackMode && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 bg-accent-red/90 text-white font-mono text-sm px-5 py-2 rounded-full shadow-lg pointer-events-none flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-white animate-ping inline-block" />
          ATTACK MODE — click a red enemy unit
        </div>
      )}

      {/* Move mode overlay banner */}
      {orderMode.active && orderMode.orderType === "MOVE_TO" && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 bg-accent-blue/90 text-white font-mono text-sm px-5 py-2 rounded-full shadow-lg pointer-events-none flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-white animate-ping inline-block" />
          MOVE MODE — click ocean destination
        </div>
      )}

      {/* Tooltip on hover */}
      {tooltip && (
        <div
          className="absolute z-50 panel px-3 py-2 text-xs font-mono pointer-events-none"
          style={{ left: tooltip.x + 14, top: tooltip.y - 10 }}
        >
          {"designation" in tooltip.object ? (
            <>
              <div className="font-semibold text-surface-100 mb-0.5">{(tooltip.object as Platform).designation}</div>
              <div className="text-surface-400 text-2xs">{(tooltip.object as Platform).type_key}</div>
              <div className="text-surface-400 text-2xs mt-0.5">
                {(tooltip.object as Platform).faction === "US" ? "FRIENDLY" : "ADVERSARY"}
                {" · "}HP: {Math.round((tooltip.object as Platform).health * 100)}%
                {" · "}Fuel: {Math.round((tooltip.object as Platform).fuel_state * 100)}%
              </div>
              {attackMode && (tooltip.object as Platform).faction !== "US" && (
                <div className="text-accent-red text-2xs mt-0.5 font-semibold">← Click to attack</div>
              )}
            </>
          ) : (
            <>
              <div className="font-semibold text-accent-amber">UNIDENTIFIED CONTACT</div>
              <div className="text-surface-400 text-2xs mt-0.5">Confidence: {Math.round((tooltip.object as IntelTrack).confidence * 100)}%</div>
            </>
          )}
        </div>
      )}

      {/* Legend */}
      <div className="absolute left-3 bottom-16 pointer-events-none flex flex-col gap-1">
        {[
          { color: "bg-[#2d7dd2]", label: "US Naval" },
          { color: "bg-[#14b8d4]", label: "US Air" },
          { color: "bg-violet-500",  label: "US Sub" },
          { color: "bg-[#ef4444]", label: "Adversary" },
          { color: "bg-[#f59e0b]", label: "Intel Track" },
        ].map((item) => (
          <div key={item.label} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${item.color}`} />
            <span className="text-2xs font-mono text-surface-400">{item.label}</span>
          </div>
        ))}
      </div>

      {/* CommandBar — always visible at bottom when a unit is selected */}
      <CommandBar />
    </div>
  );
}
