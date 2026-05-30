import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

const C: Record<string, [number, number, number, number]> = {
  US_SHIP:      [45,  125, 210, 230],
  US_AIRCRAFT:  [20,  184, 212, 230],
  US_SUBMARINE: [139, 92,  246, 230],
  US_UAV:       [34,  197, 94,  220],
  US_VEHICLE:   [249, 115, 22,  220],
  ENEMY:        [239, 68,  68,  230],
  ENEMY_AMPHIB: [255, 100, 0,   240],  // orange — amphibious assault ships
  ENEMY_TARGET: [255, 50,  50,  255],
  INTEL:        [245, 158, 11,  200],
  GHOST:        [180, 100, 40,  140],
  SELECTED:     [255, 255, 255, 255],
};

const AMPHIB_PREFIXES = ["TYPE075", "TYPE071"];

function isAmphibious(p: Platform): boolean {
  return p.faction !== "US" && AMPHIB_PREFIXES.some((pf) => p.type_key.startsWith(pf));
}

function platformColor(p: Platform, attackMode: boolean): [number, number, number, number] {
  if (p.faction !== "US") {
    if (attackMode) return C.ENEMY_TARGET;
    if (isAmphibious(p)) return C.ENEMY_AMPHIB;
    return C.ENEMY;
  }
  const key = `US_${p.platform_class}`;
  return C[key] ?? C.US_SHIP;
}

function platformRadius(p: Platform): number {
  if (p.platform_class === "SHIP" || p.platform_class === "SUBMARINE") return 9000;
  if (p.platform_class === "AIRCRAFT" || p.platform_class === "UAV") return 6000;
  return 7000;
}

// Taiwan landing zone — what the player must defend
const TAIWAN_LANDING_ZONE: [number, number] = [120.5, 23.5];
const LANDING_THREAT_RADIUS_M = 40 * 1852; // 40 NM

// ── Fog-of-War helpers ────────────────────────────────────────────────────────

// Radar detection ranges (NM) by platform class — mirrors combat.py values
const SENSOR_RANGE_NM: Record<string, number> = {
  SHIP:       200,
  AIRCRAFT:   150,
  UAV:        80,
  FACILITY:   300,
  SUBMARINE:  0,    // submarines don't emit radar
  MISSILE:    0,
  VEHICLE:    30,
};

// Sensor ring colors by class
const SENSOR_RING_COLOR: Record<string, [number, number, number, number]> = {
  SHIP:     [45,  125, 210, 35],
  AIRCRAFT: [20,  184, 212, 30],
  UAV:      [34,  197, 94,  25],
  FACILITY: [200, 200, 200, 20],
  VEHICLE:  [249, 115, 22,  20],
};

const NM_TO_M = 1852;

function haversineNm(pos1: [number, number], pos2: [number, number]): number {
  const R = 3440.065;
  const lat1 = pos1[1] * Math.PI / 180;
  const lat2 = pos2[1] * Math.PI / 180;
  const dLat = (pos2[1] - pos1[1]) * Math.PI / 180;
  const dLon = (pos2[0] - pos1[0]) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.max(0, Math.min(1, a))));
}

interface ViewState {
  longitude: number; latitude: number; zoom: number; pitch: number; bearing: number;
}

const DEFAULT_VIEW: ViewState = { longitude: 120, latitude: 20, zoom: 4, pitch: 0, bearing: 0 };

export function TheaterMap() {
  const {
    platforms, intelTracks,
    selectedPlatformId, selectPlatform,
    orderMode, setOrderMode, clearOrderMode,
    activeGame,
    setPendingWaypoint, pendingWaypoints,
    pickTargetCallback,
    pushAlert,
    combatFlashes, pruneCombatFlashes,
  } = useGameStore();

  const [viewState, setViewState] = useState<ViewState>(DEFAULT_VIEW);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; object: Platform | IntelTrack } | null>(null);
  const [animTick, setAnimTick] = useState(0);
  const [showSensorRings, setShowSensorRings] = useState(false);
  const didInitialPan = useRef(false);

  const attackMode = orderMode.active && orderMode.orderType === "ATTACK";
  const moveMode = orderMode.active && orderMode.orderType === "MOVE_TO";

  // ── Animation loop ────────────────────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => {
      setAnimTick((t) => (t + 1) % 1_000_000);
      pruneCombatFlashes();
    }, 50);
    return () => clearInterval(id);
  }, [pruneCombatFlashes]);

  // ── Auto-pan to friendly fleet on first load ─────────────────────────────
  useEffect(() => {
    if (didInitialPan.current) return;
    const friendly = Object.values(platforms).filter(
      (p) => p.faction === "US" && p.position && p.status !== "DESTROYED",
    );
    if (friendly.length < 3) return;
    didInitialPan.current = true;
    const lons = friendly.map((p) => p.position![0]);
    const lats = friendly.map((p) => p.position![1]);
    const cx = (Math.min(...lons) + Math.max(...lons)) / 2;
    const cy = (Math.min(...lats) + Math.max(...lats)) / 2;
    setViewState((vs) => ({ ...vs, longitude: cx, latitude: cy, zoom: 5 }));
  }, [platforms]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;

      if (e.key === "Escape") {
        clearOrderMode();
        selectPlatform(null);
        return;
      }

      if (!selectedPlatformId) return;
      const p = platforms[selectedPlatformId];
      if (!p || p.faction !== "US" || p.status === "DESTROYED") return;
      const gameId = activeGame?.id;

      if (e.key === "m" || e.key === "M") {
        e.preventDefault();
        clearOrderMode();
        setOrderMode({ active: true, platformId: p.id, orderType: "MOVE_TO" });
      } else if (e.key === "a" || e.key === "A") {
        e.preventDefault();
        clearOrderMode();
        setOrderMode({ active: true, platformId: p.id, orderType: "ATTACK" });
      } else if (e.key === "h" || e.key === "H") {
        e.preventDefault();
        if (gameId) {
          api.submitOrder(gameId, p.id, { order_type: "HOLD" }).catch(() => {});
          pushAlert({ level: "info", title: "Hold", body: `${p.designation} holding position` });
        }
      } else if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        if (gameId) {
          api.submitOrder(gameId, p.id, { order_type: "RTB" }).catch(() => {});
          pushAlert({ level: "info", title: "RTB", body: `${p.designation} returning to base` });
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedPlatformId, platforms, activeGame, setOrderMode, clearOrderMode, selectPlatform, pushAlert]);

  // ── Fog of War: compute which enemies are within US sensor range ──────────
  const { visibleEnemyIds, sensorRings } = useMemo(() => {
    const usList = Object.values(platforms).filter(
      (p) => p.faction === "US" && p.position && p.status !== "DESTROYED",
    );
    const enemyList = Object.values(platforms).filter(
      (p) => p.faction !== "US" && p.position && p.status !== "DESTROYED",
    );

    const visibleEnemyIds = new Set<string>();
    const rings: Array<{ position: [number, number]; radiusM: number; cls: string }> = [];

    usList.forEach((us) => {
      const rangeNm = SENSOR_RANGE_NM[us.platform_class] ?? 0;
      if (rangeNm <= 0 || !us.position) return;
      rings.push({ position: us.position, radiusM: rangeNm * NM_TO_M, cls: us.platform_class });
      enemyList.forEach((enemy) => {
        if (!enemy.position) return;
        if (haversineNm(us.position!, enemy.position) <= rangeNm) {
          visibleEnemyIds.add(enemy.id);
        }
      });
    });

    return { visibleEnemyIds, sensorRings: rings };
  }, [platforms]);

  // ── Layer data ────────────────────────────────────────────────────────────

  // Only show enemies that are currently within sensor range
  const deployedPlatforms = useMemo(
    () => Object.values(platforms).filter((p) => {
      if (!p.position || p.status === "DESTROYED") return false;
      if (p.faction === "US") return true;
      return visibleEnemyIds.has(p.id);
    }),
    [platforms, visibleEnemyIds],
  );

  // Ghost contacts: intel tracks for enemies NOT currently in sensor range
  const ghostTracks = useMemo(() => {
    const tracks = Object.values(intelTracks);
    return tracks.filter((t) => {
      // Only show tracks where the enemy isn't currently visible
      if (!t.last_position) return false;
      // Check if any tracked platform is currently visible
      // Intel tracks link to target_platform_id
      const isCurrentlyVisible = t.target_platform_id
        ? visibleEnemyIds.has(t.target_platform_id)
        : false;
      return !isCurrentlyVisible;
    });
  }, [intelTracks, visibleEnemyIds]);

  // ── Map click handler ─────────────────────────────────────────────────────
  const handleMapClick = useCallback(
    async (info: PickingInfo) => {
      const gameId = activeGame?.id;

      if (orderMode.active && orderMode.orderType === "PICK_TARGET") {
        if (info.coordinate) {
          const [lon, lat] = info.coordinate as [number, number];
          pickTargetCallback?.(lon, lat);
        }
        clearOrderMode();
        return;
      }

      if (attackMode && orderMode.platformId) {
        const clicked = info.object as Platform | IntelTrack | null;
        if (clicked && "id" in clicked) {
          let targetPos: [number, number] | null = null;
          let targetLabel = "target";

          // Visible enemy platform
          if ("faction" in clicked && (clicked as Platform).faction !== "US" && (clicked as Platform).position) {
            targetPos = (clicked as Platform).position!;
            targetLabel = (clicked as Platform).designation;
          }
          // Ghost intel track (undetected enemy)
          else if ("last_position" in clicked && (clicked as IntelTrack).last_position) {
            targetPos = (clicked as IntelTrack).last_position as [number, number];
            targetLabel = (clicked as IntelTrack).platform_type_estimate ?? "ghost contact";
          }

          if (targetPos && gameId) {
            try {
              await api.submitOrder(gameId, orderMode.platformId, {
                order_type: "MOVE_TO",
                priority: 200,
                waypoints: [{ lon: targetPos[0], lat: targetPos[1], action: "STRIKE" }],
              });
              setPendingWaypoint(orderMode.platformId, targetPos);
              const attacker = platforms[orderMode.platformId];
              const isGhost = !("faction" in clicked);
              pushAlert({
                level: "info",
                title: isGhost ? "Attack — last known position" : "Attack ordered",
                body: `${attacker?.designation ?? "Unit"} → intercepting ${targetLabel}${isGhost ? " (stale contact)" : ""}`,
              });
            } catch {
              pushAlert({ level: "warning", title: "Order failed", body: "Could not send attack order" });
            }
          }
        }
        clearOrderMode();
        return;
      }

      if (moveMode && orderMode.platformId) {
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
                title: "Move ordered",
                body: `${mover?.designation ?? "Unit"} → waypoint set`,
              });
            } catch {
              pushAlert({ level: "warning", title: "Order failed", body: "Could not send move order" });
            }
          }
          clearOrderMode();
          return;
        }
        if (info.object && "id" in info.object) {
          clearOrderMode();
          selectPlatform((info.object as Platform).id);
          return;
        }
        clearOrderMode();
        return;
      }

      // Normal selection
      if (info.object && "id" in info.object) {
        selectPlatform((info.object as Platform).id);
      } else {
        selectPlatform(null);
      }
    },
    [orderMode, attackMode, moveMode, activeGame, clearOrderMode, selectPlatform,
     setPendingWaypoint, pickTargetCallback, platforms, pushAlert],
  );

  // ── Layers ────────────────────────────────────────────────────────────────
  const layers = useMemo(() => {
    const t = animTick * 50;
    const pulse = 0.5 + 0.5 * Math.sin(t / 300);
    const now = Date.now();

    const flashLayers = combatFlashes.map((f, idx) => {
      const lifeMs = f.type === "kill" ? 4500 : f.type === "hit" ? 3000 : 1500;
      const remaining = Math.max(0, f.expires - now);
      const progress = 1 - remaining / lifeMs;
      const radius = (f.type === "kill" ? 22000 : f.type === "hit" ? 16000 : 8000) * (1 + progress * 1.5);
      const alpha = Math.round(255 * (1 - progress));
      const color: [number, number, number, number] = f.type === "kill"
        ? [255, 80, 30, alpha]
        : f.type === "hit"
        ? [255, 180, 60, alpha]
        : [200, 200, 200, Math.round(alpha * 0.5)];
      return new ScatterplotLayer({
        id: `flash-${f.id}-${idx}`,
        data: [f],
        getPosition: () => f.position,
        getRadius: radius,
        getFillColor: [color[0], color[1], color[2], 0],
        getLineColor: color,
        stroked: true,
        lineWidthMinPixels: f.type === "kill" ? 3 : 2,
        pickable: false,
      });
    });

    // Taiwan landing zone — pulsing defensive perimeter
    const landingZoneLayer = new ScatterplotLayer({
      id: "landing-zone",
      data: [{ position: TAIWAN_LANDING_ZONE, radius: LANDING_THREAT_RADIUS_M * (1 + pulse * 0.05) }],
      getPosition: (d: { position: [number, number]; radius: number }) => d.position,
      getRadius: (d: { position: [number, number]; radius: number }) => d.radius,
      getFillColor: [220, 50, 50, 12],
      getLineColor: [220, 50, 50, 80],
      stroked: true,
      lineWidthMinPixels: 1,
      pickable: false,
      updateTriggers: { getRadius: [pulse] },
    });

    // Sensor coverage rings (shown when toggle is on)
    const sensorRingLayer = showSensorRings ? new ScatterplotLayer({
      id: "sensor-rings",
      data: sensorRings,
      getPosition: (d: typeof sensorRings[0]) => d.position,
      getRadius: (d: typeof sensorRings[0]) => d.radiusM,
      getFillColor: (d: typeof sensorRings[0]) => {
        const c = SENSOR_RING_COLOR[d.cls] ?? [100, 100, 100, 15];
        return [c[0], c[1], c[2], 12];
      },
      getLineColor: (d: typeof sensorRings[0]) => {
        const c = SENSOR_RING_COLOR[d.cls] ?? [100, 100, 100, 40];
        return [c[0], c[1], c[2], 50];
      },
      stroked: true,
      lineWidthMinPixels: 1,
      pickable: false,
    }) : null;

    // Ghost contacts layer (intel tracks for undetected enemies)
    const ghostContactLayer = new ScatterplotLayer<IntelTrack>({
      id: "ghost-contacts",
      data: ghostTracks,
      getPosition: (d) => d.last_position as [number, number],
      getRadius: (_d: IntelTrack) => 11000 * (1 + (attackMode ? pulse * 0.4 : 0)),
      getFillColor: (d: IntelTrack) => {
        const alpha = Math.round(d.confidence * 100);
        return attackMode ? [239, 100, 40, alpha] : [200, 120, 40, alpha];
      },
      getLineColor: (d: IntelTrack) => {
        if (attackMode) return [255, 120, 40, 200];
        return [245, 158, 11, Math.round(d.confidence * 180)];
      },
      stroked: true,
      lineWidthMinPixels: 1,
      pickable: true,
      onClick: (info: PickingInfo) => {
        if (info.object) setTooltip({ x: info.x ?? 0, y: info.y ?? 0, object: info.object as IntelTrack });
        return true;
      },
      onHover: (info: PickingInfo) => {
        if (info.object && info.x !== undefined) setTooltip({ x: info.x, y: info.y, object: info.object as IntelTrack });
        else setTooltip(null);
      },
      updateTriggers: { getRadius: [attackMode, pulse], getFillColor: [attackMode], getLineColor: [attackMode] },
    });

    return [
      // Sensor rings (optional)
      ...(sensorRingLayer ? [sensorRingLayer] : []),

      // Ghost intel contacts (undetected enemies)
      ghostContactLayer,

      // Selection ring
      ...(selectedPlatformId && platforms[selectedPlatformId]?.position ? [
        new ScatterplotLayer({
          id: "selected-ring",
          data: [platforms[selectedPlatformId]],
          getPosition: (d: unknown) => (d as Platform).position!,
          getRadius: platformRadius(platforms[selectedPlatformId]) * (2.0 + pulse * 0.3),
          getFillColor: [0, 0, 0, 0],
          getLineColor: [255, 255, 255, 200],
          stroked: true,
          lineWidthMinPixels: 1.5,
          pickable: false,
          updateTriggers: { getRadius: [pulse] },
        }),
      ] : []),

      // Platform dots (US + currently-detected enemies)
      new ScatterplotLayer<Platform>({
        id: "platforms",
        data: deployedPlatforms,
        getPosition: (d) => d.position!,
        getRadius: (d) => {
          const base = platformRadius(d);
          if (attackMode && d.faction !== "US") return base * (1 + pulse * 0.5);
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
          if (info.object) selectPlatform((info.object as Platform).id);
          return true;
        },
        onHover: (info: PickingInfo) => {
          if (info.object && info.x !== undefined) setTooltip({ x: info.x, y: info.y, object: info.object as Platform });
          else setTooltip(null);
        },
        transitions: { getPosition: 600 },
        updateTriggers: {
          getRadius: [attackMode, pulse],
          getFillColor: [selectedPlatformId, attackMode],
          getLineColor: [selectedPlatformId, attackMode],
        },
      }),

      // Pending waypoint paths
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

      // Heading indicators
      new PathLayer({
        id: "headings",
        data: deployedPlatforms.filter((p) => p.faction === "US" && (p.speed ?? 0) > 0.5),
        getPath: (d: Platform) => {
          if (!d.position || d.heading == null) return [d.position!, d.position!];
          const [lon, lat] = d.position;
          const headingRad = (d.heading * Math.PI) / 180;
          const dist = 0.4;
          const dlat = Math.cos(headingRad) * dist;
          const dlon = Math.sin(headingRad) * dist / Math.max(0.1, Math.cos((lat * Math.PI) / 180));
          return [d.position, [lon + dlon, lat + dlat]];
        },
        getColor: [120, 200, 255, 200],
        getWidth: 1.5,
        widthUnits: "pixels",
      }),

      // Friendly labels (close zoom)
      new TextLayer<Platform>({
        id: "platform-labels",
        data: deployedPlatforms.filter((p) => p.faction === "US"),
        getPosition: (d) => d.position!,
        getText: (d) => d.designation.split(" ").slice(0, 2).join(" "),
        getSize: 10,
        getColor: [160, 190, 220, 200],
        getPixelOffset: [0, -16],
        fontFamily: "JetBrains Mono, monospace",
        fontWeight: 500,
        visible: viewState.zoom > 6,
      }),

      // Enemy labels for confirmed contacts at zoom
      new TextLayer<Platform>({
        id: "enemy-labels",
        data: deployedPlatforms.filter((p) => p.faction !== "US"),
        getPosition: (d) => d.position!,
        getText: (d) => d.type_key.split("_")[0],
        getSize: 9,
        getColor: [239, 68, 68, 180],
        getPixelOffset: [0, -14],
        fontFamily: "JetBrains Mono, monospace",
        fontWeight: 500,
        visible: viewState.zoom > 6,
      }),

      // Landing zone perimeter
      landingZoneLayer,

      // Combat flash markers
      ...flashLayers,
    ];
  }, [
    deployedPlatforms, ghostTracks, sensorRings, selectedPlatformId,
    viewState.zoom, pendingWaypoints, platforms, attackMode,
    selectPlatform, animTick, combatFlashes, showSensorRings,
  ]);

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
        <Map mapStyle={MAP_STYLE as never} style={{ width: "100%", height: "100%" }}>
          <NavigationControl position="bottom-right" />
          <ScaleControl position="bottom-left" unit="nautical" />
        </Map>
      </DeckGL>

      {attackMode && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 bg-accent-red/95 text-white font-mono text-sm px-5 py-2 rounded-full shadow-lg pointer-events-none flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-white animate-ping inline-block" />
          ATTACK MODE — click red enemy or amber ghost contact
        </div>
      )}

      {moveMode && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 bg-accent-blue/95 text-white font-mono text-sm px-5 py-2 rounded-full shadow-lg pointer-events-none flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-white animate-ping inline-block" />
          MOVE MODE — click any ocean tile
        </div>
      )}

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
                <div className="text-accent-red text-2xs mt-0.5 font-semibold">→ Click to attack</div>
              )}
            </>
          ) : (
            <>
              <div className="font-semibold text-accent-amber">GHOST CONTACT</div>
              <div className="text-surface-400 text-2xs">
                {(tooltip.object as IntelTrack).platform_type_estimate ?? "Unknown type"}
              </div>
              <div className="text-surface-400 text-2xs mt-0.5">
                Confidence: {Math.round((tooltip.object as IntelTrack).confidence * 100)}%
                {" · "}{(tooltip.object as IntelTrack).track_type}
              </div>
              <div className="text-surface-500 text-2xs">
                Last seen T+{(tooltip.object as IntelTrack).last_updated_tick}
              </div>
              {attackMode && (
                <div className="text-accent-amber text-2xs mt-0.5 font-semibold">→ Click to attack last position</div>
              )}
            </>
          )}
        </div>
      )}

      {/* Map controls */}
      <div className="absolute top-3 right-3 z-20 flex flex-col gap-1">
        <button
          onClick={() => setShowSensorRings((v) => !v)}
          className={`px-2.5 py-1 text-2xs font-mono rounded border transition-colors ${
            showSensorRings
              ? "bg-accent-blue/30 border-accent-blue/60 text-accent-blue"
              : "bg-surface-800/80 border-surface-600 text-surface-400 hover:text-surface-200"
          }`}
          title="Toggle sensor coverage rings"
        >
          SENSORS
        </button>
      </div>

      {/* Legend */}
      <div className="absolute left-3 bottom-24 pointer-events-none flex flex-col gap-1">
        {[
          { color: "bg-[#2d7dd2]", label: "US Naval" },
          { color: "bg-[#14b8d4]", label: "US Air" },
          { color: "bg-violet-500",  label: "US Sub" },
          { color: "bg-[#ef4444]", label: "PLAN surface" },
          { color: "bg-orange-500", label: "PLAN amphibious" },
          { color: "bg-[#f59e0b]", label: "Ghost contact" },
          { color: "bg-red-700 border border-red-500", label: "Taiwan LZ — defend" },
        ].map((item) => (
          <div key={item.label} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${item.color}`} />
            <span className="text-2xs font-mono text-surface-400">{item.label}</span>
          </div>
        ))}
      </div>

      <CommandBar />
    </div>
  );
}
