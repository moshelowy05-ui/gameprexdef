import { io, Socket } from "socket.io-client";
import { useGameStore } from "@/store/gameStore";
import type { PlatformDelta, CombatEvent, IntelUpdate, GameOverData, ScenarioEvent } from "@/types";

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (!socket) {
    socket = io("/", {
      path: "/socket.io",
      transports: ["websocket"],
      withCredentials: true,
      autoConnect: false,
    });

    socket.on("tick", (data: { tick: number; paused: boolean }) => {
      useGameStore.getState().updateTick(data.tick, data.paused);
    });

    socket.on("platform_updates", (deltas: PlatformDelta[]) => {
      useGameStore.getState().applyPlatformDeltas(deltas);
    });

    socket.on("alert", (alert: { level: "info" | "warning" | "critical"; title: string; body: string }) => {
      useGameStore.getState().pushAlert(alert);
    });

    socket.on("combat_events", (events: CombatEvent[]) => {
      const store = useGameStore.getState();
      store.addCombatEvents(events);
      const platforms = store.platforms;
      for (const ev of events) {
        // Visual flash on the target's location
        const target = platforms[ev.target_id];
        const pos = target?.position;
        if (pos) {
          const type = !ev.hit ? "miss" : ev.target_health_after <= 0 ? "kill" : "hit";
          store.pushCombatFlash({ position: pos as [number, number], type });
        }
        // Alerts for hits
        if (ev.hit && ev.target_health_after <= 0) {
          store.pushAlert({
            level: "critical",
            title: `KILL — ${target?.designation ?? "target destroyed"}`,
            body: ev.narrative,
          });
        } else if (ev.hit && ev.damage >= 0.5) {
          store.pushAlert({
            level: "critical",
            title: `HEAVY HIT — ${ev.weapon_type.replace("_WEAPON", "")}`,
            body: ev.narrative,
          });
        } else if (ev.hit) {
          store.pushAlert({
            level: "warning",
            title: "ENGAGEMENT",
            body: ev.narrative,
          });
        }
      }
    });

    socket.on("intel_updates", (updates: IntelUpdate[]) => {
      useGameStore.getState().updateIntelTracks(updates);
    });

    socket.on("game_over", (data: GameOverData) => {
      useGameStore.getState().setGameOver(data);
      useGameStore.getState().pushAlert({
        level: data.winner === "US" ? "info" : "critical",
        title: `GAME OVER — ${data.winner === "DRAW" ? "STALEMATE" : data.winner + " VICTORY"}`,
        body: data.reason,
      });
    });

    socket.on("mission_updates", (updates: Array<{ id: string; status: string; [key: string]: unknown }>) => {
      useGameStore.getState().applyMissionUpdates(updates);
    });

    socket.on("production_deliveries", (deliveries: Array<{ facility_id: string; type_key: string; platform_id: string; tick: number }>) => {
      deliveries.forEach(d => {
        useGameStore.getState().pushAlert({
          level: "info",
          title: "Production Delivery",
          body: `${d.type_key} delivered from facility`,
        });
      });
    });

    socket.on("scenario_event", (event: ScenarioEvent) => {
      useGameStore.getState().pushScenarioEvent(event);
    });
  }
  return socket;
}

export function connectToGame(gameId: string): void {
  const s = getSocket();
  if (!s.connected) s.connect();
  s.emit("join_game", { game_id: gameId });
}

export function disconnectSocket(): void {
  if (socket?.connected) socket.disconnect();
}
