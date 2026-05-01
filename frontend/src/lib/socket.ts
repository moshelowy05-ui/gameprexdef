import { io, Socket } from "socket.io-client";
import { useGameStore } from "@/store/gameStore";
import type { Platform } from "@/types";

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

    socket.on("platform_updates", (deltas: Platform[]) => {
      const store = useGameStore.getState();
      deltas.forEach((p) => store.updatePlatform(p));
    });

    socket.on(
      "alert",
      (alert: { level: "info" | "warning" | "critical"; title: string; body: string }) => {
        useGameStore.getState().pushAlert(alert);
      }
    );

    socket.on("combat_event", (event: { narrative: string; event_type: string }) => {
      useGameStore.getState().pushAlert({
        level: "warning",
        title: `COMBAT: ${event.event_type}`,
        body: event.narrative,
      });
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
