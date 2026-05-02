import { useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { HealthBar } from "@/components/ui/HealthBar";
import { Factory, Package, TrendingUp, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

const PLATFORM_OPTIONS: Record<string, string[]> = {
  SHIPYARD: ["DDG_51", "CG_47", "LCS_1", "LHD_1", "LPD_17", "SSN_774"],
  AIRCRAFT_FACTORY: ["F35C", "F18E", "EA18G", "MH60R", "P8A", "RQ4"],
  MISSILE_PLANT: ["VLS_SM6", "VLS_TLAM", "VLS_ESSM"],
};

interface QueueFormState {
  platform_type_key: string;
  quantity: number;
}

function QueueOrderForm({
  facilityId,
  facilityType,
  gameId,
  onClose,
}: {
  facilityId: string;
  facilityType: string;
  gameId: string;
  onClose: () => void;
}) {
  const options = PLATFORM_OPTIONS[facilityType] ?? [];
  const [form, setForm] = useState<QueueFormState>({
    platform_type_key: options[0] ?? "",
    quantity: 1,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!form.platform_type_key) return;
    setLoading(true);
    setError(null);
    try {
      await api.queueProduction(gameId, facilityId, {
        platform_type_key: form.platform_type_key,
        quantity: form.quantity,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to queue order");
    } finally {
      setLoading(false);
    }
  };

  if (options.length === 0) {
    return (
      <div className="px-3 pb-2">
        <div className="bg-surface-800 rounded p-2 text-2xs font-mono text-surface-400">
          No orderable types for this facility.
        </div>
        <button
          onClick={onClose}
          className="mt-1 w-full text-2xs font-mono text-surface-400 hover:text-surface-200 transition-colors"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="px-3 pb-2 space-y-1.5 bg-surface-900/50 border-t border-surface-700">
      <div className="pt-2 text-2xs font-mono text-surface-400 uppercase tracking-widest">
        Queue Production Order
      </div>
      {error && (
        <div className="text-2xs font-mono text-accent-red">{error}</div>
      )}
      <div className="space-y-1">
        <label className="text-2xs font-mono text-surface-500">Platform Type</label>
        <select
          value={form.platform_type_key}
          onChange={(e) => setForm((f) => ({ ...f, platform_type_key: e.target.value }))}
          className="w-full bg-surface-800 border border-surface-600 rounded px-2 py-1 text-xs font-mono text-surface-200 focus:outline-none focus:border-accent-blue"
        >
          {options.map((key) => (
            <option key={key} value={key}>
              {key}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <label className="text-2xs font-mono text-surface-500">Quantity (1–20)</label>
        <input
          type="number"
          min={1}
          max={20}
          value={form.quantity}
          onChange={(e) =>
            setForm((f) => ({ ...f, quantity: Math.max(1, Math.min(20, Number(e.target.value))) }))
          }
          className="w-full bg-surface-800 border border-surface-600 rounded px-2 py-1 text-xs font-mono text-surface-200 focus:outline-none focus:border-accent-blue"
        />
      </div>
      <div className="flex gap-1 pt-0.5">
        <button
          onClick={onClose}
          className="flex-1 px-2 py-1.5 text-2xs font-mono rounded bg-surface-700 hover:bg-surface-600 text-surface-300 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={loading || !form.platform_type_key}
          className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-2xs font-mono rounded bg-accent-blue hover:bg-accent-blue/80 text-white transition-colors disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
          Submit
        </button>
      </div>
    </div>
  );
}

export function DIBPanel() {
  const { facilities, activeGame } = useGameStore();
  const [openFormId, setOpenFormId] = useState<string | null>(null);
  const [cancelingId, setCancelingId] = useState<string | null>(null);

  const allFacilities = Object.values(facilities);
  const productionFacilities = allFacilities.filter((f) =>
    ["SHIPYARD", "AIRCRAFT_FACTORY", "MISSILE_PLANT", "MUNITIONS_DEPOT"].includes(f.facility_type)
  );

  const totalOrders = allFacilities.reduce(
    (sum, f) => sum + (f.production_queue as unknown[]).length,
    0
  );

  const activelyProducing = allFacilities.filter(
    (f) => (f.production_queue as unknown[]).length > 0
  ).length;

  const gameId = activeGame?.id ?? "";

  const handleCancelOrder = async (facilityId: string, orderId: string) => {
    if (!gameId) return;
    setCancelingId(orderId);
    try {
      await api.cancelProduction(gameId, facilityId, orderId);
    } finally {
      setCancelingId(null);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="panel-header">
        <span className="panel-title">Industrial Base</span>
        <span className="text-2xs font-mono text-surface-400">{totalOrders} orders</span>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-px bg-surface-700 border-b border-surface-700">
        {[
          { label: "Facilities",  value: productionFacilities.length,  icon: <Factory className="w-3 h-3" /> },
          { label: "Prod Orders", value: totalOrders,                   icon: <Package className="w-3 h-3" /> },
          { label: "Producing",   value: activelyProducing,             icon: <TrendingUp className="w-3 h-3" /> },
        ].map((stat) => (
          <div key={stat.label} className="bg-surface-900 px-3 py-2 flex items-center gap-2">
            <span className="text-surface-400">{stat.icon}</span>
            <div>
              <div className="stat-value text-sm">{stat.value}</div>
              <div className="stat-label">{stat.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Facility list */}
      <div className="flex-1 overflow-y-auto">
        {productionFacilities.length === 0 && (
          <div className="px-3 py-8 text-center">
            <Factory className="w-6 h-6 mx-auto mb-2 text-surface-600" />
            <p className="text-xs font-mono text-surface-500">No production facilities</p>
            <p className="text-2xs font-mono text-surface-600 mt-1">Load a scenario to begin</p>
          </div>
        )}
        {productionFacilities.map((f) => {
          const queue = f.production_queue as Array<{
            id?: string;
            platform_type_key: string;
            quantity: number;
            quantity_complete: number;
            ticks_elapsed: number;
            ticks_per_unit: number;
          }>;
          const activeOrder = queue[0];
          const progress = activeOrder
            ? activeOrder.ticks_per_unit > 0
              ? activeOrder.ticks_elapsed / activeOrder.ticks_per_unit
              : 0
            : 0;
          const ticksRemaining = activeOrder
            ? Math.max(0, activeOrder.ticks_per_unit - activeOrder.ticks_elapsed)
            : 0;
          const isFormOpen = openFormId === f.id;

          return (
            <div key={f.id} className="border-b border-surface-800">
              <div className="px-3 py-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono text-surface-100 truncate">{f.name}</span>
                  <StatusBadge status={f.power_state} />
                </div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-2xs font-mono text-surface-400 uppercase">{f.facility_type}</span>
                  <span className="text-2xs font-mono text-surface-500">{f.production_slots} slot{f.production_slots > 1 ? "s" : ""}</span>
                </div>
                <HealthBar value={f.health} label="Cond" />
              </div>

              {activeOrder && (
                <div className="px-3 pb-2 space-y-1">
                  <div className="flex justify-between text-2xs font-mono">
                    <span className="text-surface-400">Producing:</span>
                    <span className="text-surface-200">{activeOrder.platform_type_key}</span>
                  </div>
                  <div className="flex justify-between text-2xs font-mono">
                    <span className="text-surface-400">Progress:</span>
                    <span className="text-surface-200">
                      {activeOrder.quantity_complete}/{activeOrder.quantity}
                    </span>
                  </div>
                  <div className="flex justify-between text-2xs font-mono">
                    <span className="text-surface-400">ETA:</span>
                    <span className="data-val">{ticksRemaining} ticks</span>
                  </div>
                  <HealthBar value={progress} label="Prog" />

                  {/* Queued items with cancel buttons */}
                  {queue.length > 1 && (
                    <div className="mt-1 space-y-0.5">
                      {queue.slice(1).map((item, idx) => {
                        const orderId = item.id ?? `${f.id}-q-${idx}`;
                        return (
                          <div key={orderId} className="flex items-center justify-between text-2xs font-mono text-surface-500">
                            <span>
                              {item.platform_type_key} ×{item.quantity}
                            </span>
                            <button
                              onClick={() => handleCancelOrder(f.id, orderId)}
                              disabled={cancelingId === orderId}
                              className="ml-1 p-0.5 rounded hover:bg-accent-red/20 text-surface-500 hover:text-accent-red transition-colors disabled:opacity-50"
                              title="Cancel order"
                            >
                              {cancelingId === orderId ? (
                                <Loader2 className="w-2.5 h-2.5 animate-spin" />
                              ) : (
                                <X className="w-2.5 h-2.5" />
                              )}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Queue Order button */}
              <div className="px-3 pb-2">
                {!isFormOpen ? (
                  <button
                    onClick={() => setOpenFormId(f.id)}
                    className="w-full px-2 py-1 text-2xs font-mono rounded bg-surface-800 hover:bg-surface-700 text-surface-400 hover:text-surface-200 border border-surface-700 hover:border-surface-600 transition-colors"
                  >
                    + Queue Order
                  </button>
                ) : null}
              </div>

              {/* Slide-down queue form */}
              {isFormOpen && (
                <QueueOrderForm
                  facilityId={f.id}
                  facilityType={f.facility_type}
                  gameId={gameId}
                  onClose={() => setOpenFormId(null)}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
