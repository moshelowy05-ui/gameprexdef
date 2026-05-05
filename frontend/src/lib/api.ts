const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "API error");
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Auth
  login: (username: string, password: string) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request("/auth/logout", { method: "POST" }),
  me: () => request("/auth/me"),

  // Game
  createGame: (scenario_id: string) =>
    request("/game/create", { method: "POST", body: JSON.stringify({ scenario_id }) }),
  listGames: () => request("/game/list"),
  getGame: (id: string) => request(`/game/${id}`),
  getGameState: (id: string) => request(`/game/${id}/state`),
  pauseGame: (id: string) => request(`/game/${id}/pause`, { method: "POST" }),
  resumeGame: (id: string) => request(`/game/${id}/resume`, { method: "POST" }),
  setSpeed: (id: string, multiplier: number) =>
    request(`/game/${id}/speed?multiplier=${multiplier}`, { method: "POST" }),

  // Platforms
  listPlatformTypes: (params?: { category?: string; faction?: string }) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return request(`/platforms/types${q ? `?${q}` : ""}`);
  },
  getPlatformType: (key: string) => request(`/platforms/types/${key}`),
  listPlatforms: (gameId: string, params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request(`/platforms/${gameId}${q ? `?${q}` : ""}`);
  },
  getPlatform: (gameId: string, platformId: string) =>
    request(`/platforms/${gameId}/${platformId}`),

  // Task Forces
  listTaskForces: (gameId: string) => request(`/task-forces/${gameId}`),
  createTaskForce: (gameId: string, data: { name: string; commander_unit_id: string; assigned_unit_ids?: string[] }) =>
    request(`/task-forces/`, { method: "POST", body: JSON.stringify({ game_id: gameId, ...data }) }),

  addToTaskForce: (gameId: string, tfId: string, unitIds: string[]) =>
    request(`/task-forces/${gameId}/${tfId}/units`, { method: "POST", body: JSON.stringify({ unit_ids: unitIds }) }),

  removeFromTaskForce: (gameId: string, tfId: string, unitId: string) =>
    request(`/task-forces/${gameId}/${tfId}/units/${unitId}`, { method: "DELETE" }),

  // Missions
  listMissions: (gameId: string, status?: string) =>
    request(`/missions/${gameId}${status ? `?status=${status}` : ""}`),
  createMission: (gameId: string, data: {
    name: string;
    mission_type: string;
    assigned_tf_id: string;
    target: { lon: number; lat: number };
    priority: number;
    start_tick: number;
    commander_notes?: string;
    waypoints?: Array<{ lon: number; lat: number }>;
  }) =>
    request("/missions/", { method: "POST", body: JSON.stringify({ game_id: gameId, ...data }) }),
  updateMissionStatus: (gameId: string, missionId: string, status: string) =>
    request(`/missions/${gameId}/${missionId}/status?status=${status}`, { method: "PATCH" }),

  // Facilities
  listFacilities: (gameId: string, params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request(`/facilities/${gameId}${q ? `?${q}` : ""}`);
  },
  queueProduction: (
    gameId: string,
    facilityId: string,
    data: { platform_type_key: string; quantity: number; priority?: number; surge_mode?: boolean }
  ) =>
    request(`/facilities/${gameId}/${facilityId}/production`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  cancelProduction: (gameId: string, facilityId: string, orderId: string) =>
    request(`/facilities/${gameId}/${facilityId}/production/${orderId}`, { method: "DELETE" }),

  // Intel
  listTracks: (gameId: string, params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return request(`/intel/${gameId}/tracks${q ? `?${q}` : ""}`);
  },

  // DIB
  getResources: (gameId: string) => request(`/dib/${gameId}/resources`),
  getProductionSummary: (gameId: string) => request(`/dib/${gameId}/production-summary`),

  // Platform orders
  submitOrder: (
    gameId: string,
    platformId: string,
    order: {
      order_type: "MOVE_TO" | "HOLD" | "RTB" | "PATROL" | "ABORT";
      priority?: number;
      waypoints?: Array<{ lon: number; lat: number; action?: string; speed_override_knots?: number }>;
      target_speed_knots?: number;
    }
  ) =>
    request(`/platforms/${gameId}/${platformId}/orders`, {
      method: "POST",
      body: JSON.stringify(order),
    }),

  cancelOrders: (gameId: string, platformId: string) =>
    request(`/platforms/${gameId}/${platformId}/orders`, { method: "DELETE" }),
};
