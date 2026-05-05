import { useCallback, useEffect, useMemo, useState } from "react";
import Map, { NavigationControl, ScaleControl } from "react-map-gl/maplibre";
import { DeckGL } from "@deck.gl/react";
import { ScatterplotLayer, TextLayer, PathLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import { useGameStore } from "@/store/gameStore";
import { api } from "@/lib/api";
import type { Platform, IntelTrack } from "@/types";
import "maplibre-gl/dist/maplibre-gl.css";

// Dark tactical map style
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
  layers: [
    {
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
    },
  ],
};

const PLATFORM_COLORS: Record<string, [number, number, number, number]> = {
  US_SHIP:       [45, 125, 210, 220],
  US_AIRCRAFT:   [20, 184, 212, 220],
  US_SUBMARINE:  [139, 92, 246, 220],
  US_UAV:        [34, 197, 94, 200],
  US_VEHICLE:    [249, 115, 22, 200],
  US_SATELLITE:  [20, 184, 212, 150],
  ADVERSARY:     [239, 68, 68, 220],
  INTEL:         [245, 158, 11, 180],
};

function platformColor(p: Platform): [number, number, number, number] {
  if (p.faction !== "US") return PLATFORM_COLORS.ADVERSARY;
  const key = `US_${p.platform_class}`;
  return PLATFORM_COLORS[key] ?? PLATFORM_COLORS.US_SHIP;
}

interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
}

const DEFAULT_VIEW: ViewState = {
  longitude: 120,
  latitude: 20,
  zoom: 4,
  pitch: 0,
  bearing: 0,
};

export function TheaterMap() {
  const { platforms, intelTracks, selectedPlatformId, selectPlatform, orderMode, clearOrderMode, activeGame, setPendingWaypoint, pendingWaypoints } = useGameStore();
  const [viewState, setViewState] = useState<ViewState>(DEFAULT_VIEW);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; object: Platform | IntelTrack } | null>(null);

  const handleMapClick = useCallback(
    async (info: PickingInfo) => {
      // If in order-mode and clicked empty map → submit MOVE_TO order
      if (orderMode.active && orderMode.platformId && orderMode.orderType === "MOVE_TO") {
        if (!info.object && info.coordinate) {
          const [lon, lat] = info.coordinate as [number, number];
          const gameId = activeGame?.id;
          if (gameId) {
            try {
              await api.submitOrder(gameId, orderMode.platformId, {
                order_type: "MOVE_TO",
                priority: 200,
                waypoints: [{ lon, lat, action: "TRANSIT" }],
              });
              setPendingWaypoint(orderMode.platformId, [lon, lat]);
            } catch (e) {
              console.error("Order failed:", e);
            }
          }
          clearOrderMode();
          return;
        }
        // Clicked on a platform in order mode → also exit order mode
        if (info.object) {
          clearOrderMode();
        }
      }
      // Normal platform selection
      if (info.object && "id" in info.object) {
        selectPlatform((info.object as { id: string }).id);
      } else if (!info.object) {
        selectPlatform(null);
      }
    },
    [orderMode, activeGame, clearOrderMode, selectPlatform, setPendingWaypoint]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && orderMode.active) clearOrderMode();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [orderMode.active, clearOrderMode]);

  const deployedPlatforms = useMemo(
    () => Object.values(platforms).filter((p) => p.position !== null && p.status !== "DESTROYED"),
    [platforms]
  );

  const activeTracks = useMemo(
    () => Object.values(intelTracks),
    [intelTracks]
  );

  const layers = useMemo(() => [
    // Intel tracks (unknown contacts)
    new ScatterplotLayer<IntelTrack>({
      id: "intel-tracks",
      data: activeTracks,
      getPosition: (d) => d.last_position,
      getRadius: 12000,
      getFillColor: (d) => {
        const alpha = Math.round(d.confidence * 180);
        return [245, 158, 11, alpha];
      },
      getLineColor: [245, 158, 11, 120],
      stroked: true,
      lineWidthMinPixels: 1,
      pickable: true,
    }),

    // Platform dots
    new ScatterplotLayer<Platform>({
      id: "platforms",
      data: deployedPlatforms,
      getPosition: (d) => d.position!,
      getRadius: (d) => {
        if (d.platform_class === "SHIP" || d.platform_class === "SUBMARINE") return 8000;
        if (d.platform_class === "AIRCRAFT" || d.platform_class === "UAV") return 5000;
        return 6000;
      },
      getFillColor: (d) => {
        const c = platformColor(d);
        if (d.id === selectedPlatformId) return [255, 255, 255, 255];
        return c;
      },
      getLineColor: (d) => {
        if (d.id === selectedPlatformId) return [45, 125, 210, 255];
        return [255, 255, 255, 60];
      },
      stroked: true,
      lineWidthMinPixels: 1,
      pickable: true,
      onClick: (info: PickingInfo) => {
        if (info.object) selectPlatform((info.object as Platform).id);
        return true;
      },
      onHover: (info: PickingInfo) => {
        if (info.object && info.x !== undefined) {
          setTooltip({ x: info.x, y: info.y, object: info.object as Platform });
        } else {
          setTooltip(null);
        }
      },
    }),

    // Waypoint paths for platforms with pending MOVE_TO orders
    new PathLayer({
      id: "waypoint-paths",
      data: Object.entries(pendingWaypoints).flatMap(([platformId, dest]) => {
        const platform = platforms[platformId];
        if (!platform?.position) return [];
        return [{ platformId, path: [platform.position, dest] }];
      }),
      getPath: (d) => (d as { path: [number, number][] }).path,
      getColor: [45, 125, 210, 180],
      getWidth: 2,
      widthUnits: "pixels",
      getDashArray: [6, 4],
      dashJustified: true,
      extensions: [],
    }),

    // Platform labels (visible at closer zoom)
    new TextLayer<Platform>({
      id: "platform-labels",
      data: deployedPlatforms.filter((p) => p.faction === "US"),
      getPosition: (d) => d.position!,
      getText: (d) => d.designation.split(" ").slice(0, 2).join(" "),
      getSize: 10,
      getColor: [180, 200, 220, 180],
      getPixelOffset: [0, -14],
      fontFamily: "JetBrains Mono, monospace",
      fontWeight: 500,
      visible: viewState.zoom > 6,
    }),
  ], [deployedPlatforms, activeTracks, selectedPlatformId, selectPlatform, viewState.zoom, pendingWaypoints, platforms]);

  return (
    <div className="relative w-full h-full bg-surface-950">
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: vs }) => setViewState(vs as ViewState)}
        controller={true}
        layers={layers}
        style={{ position: "absolute", inset: "0" }}
        onClick={handleMapClick}
        getCursor={() => orderMode.active ? "crosshair" : "auto"}
      >
        <Map
          mapStyle={MAP_STYLE as never}
          style={{ width: "100%", height: "100%" }}
        >
          <NavigationControl position="bottom-right" />
          <ScaleControl position="bottom-left" unit="nautical" />
        </Map>
      </DeckGL>

      {/* Order mode hint */}
      {orderMode.active && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 bg-accent-blue/90 text-white font-mono text-xs px-4 py-2 rounded-full shadow-lg pointer-events-none">
          Click destination on map — press ESC to cancel
        </div>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div
          className="absolute z-50 panel px-3 py-2 text-xs font-mono pointer-events-none"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          {"designation" in tooltip.object ? (
            <>
              <div className="font-semibold text-surface-100">{tooltip.object.designation}</div>
              <div className="text-surface-400 text-2xs">{tooltip.object.type_key}</div>
              <div className="text-surface-400 text-2xs mt-0.5">
                Fuel: {Math.round(tooltip.object.fuel_state * 100)}% | HP: {Math.round(tooltip.object.health * 100)}%
              </div>
            </>
          ) : (
            <>
              <div className="font-semibold text-accent-amber">TRACK</div>
              <div className="text-surface-400 text-2xs">{(tooltip.object as IntelTrack).track_type}</div>
              <div className="text-surface-400 text-2xs">
                Conf: {Math.round((tooltip.object as IntelTrack).confidence * 100)}%
              </div>
            </>
          )}
        </div>
      )}

      {/* Grid overlay — tactical look */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute bottom-8 left-3 flex flex-col gap-1">
          {[
            { color: "bg-accent-blue", label: "US Naval" },
            { color: "bg-accent-cyan", label: "US Air" },
            { color: "bg-violet-500", label: "US Sub" },
            { color: "bg-accent-red", label: "Adversary" },
            { color: "bg-accent-amber", label: "Intel Track" },
          ].map((item) => (
            <div key={item.label} className="flex items-center gap-1.5">
              <div className={`w-2 h-2 rounded-full ${item.color}`} />
              <span className="text-2xs font-mono text-surface-400">{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
