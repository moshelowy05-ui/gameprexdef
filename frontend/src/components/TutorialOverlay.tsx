/**
 * TutorialOverlay — first-time onboarding for new commanders.
 * Shown once per browser; dismissed by clicking 'Got it' or pressing any key.
 * Persisted via localStorage so returning players don't see it again.
 */
import { useEffect, useState } from "react";
import { Play, MousePointerClick, Crosshair, Keyboard, X } from "lucide-react";

const STORAGE_KEY = "gameprex.tutorial.seen.v1";

export function TutorialOverlay() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      setVisible(true);
    }
  }, []);

  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " " || e.key === "Escape") {
        e.preventDefault();
        dismiss();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [visible]);

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, "1");
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm flex items-center justify-center p-6 pointer-events-auto">
      <div className="panel max-w-lg w-full p-6 relative">
        <button
          onClick={dismiss}
          className="absolute top-3 right-3 text-surface-500 hover:text-surface-200 transition-colors"
          title="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>

        <h2 className="text-base font-mono font-semibold text-surface-100 mb-1 tracking-wide uppercase">
          Welcome, Commander
        </h2>
        <p className="text-2xs font-mono text-surface-400 mb-5 tracking-widest uppercase">
          Quick brief — you'll be in the field in 30 seconds
        </p>

        <div className="space-y-4">
          <Row
            icon={<Play className="w-4 h-4 text-accent-amber" />}
            title="1. Press Play to start"
            body="The game is paused — click the ▶ button at the top, or press SPACE."
          />
          <Row
            icon={<MousePointerClick className="w-4 h-4 text-accent-blue" />}
            title="2. Select units"
            body={
              <>
                Click a blue dot to select it. <span className="text-accent-blue">Shift-click</span> to add more units,
                or use <span className="text-accent-blue">SELECT ALL</span> in the Forces panel — orders then apply to the whole group.
              </>
            }
          />
          <Row
            icon={<Crosshair className="w-4 h-4 text-accent-red" />}
            title="3. Move or Attack"
            body={
              <>
                <span className="text-accent-blue">Move</span> — click ocean to set destination.{" "}
                <span className="text-accent-red">Attack</span> — click a red enemy to intercept and engage.
              </>
            }
          />
          <Row
            icon={<Keyboard className="w-4 h-4 text-surface-300" />}
            title="4. Keyboard shortcuts"
            body={
              <span className="font-mono">
                <kbd className="kbd">M</kbd> Move · <kbd className="kbd">A</kbd> Attack ·{" "}
                <kbd className="kbd">H</kbd> Hold · <kbd className="kbd">R</kbd> RTB · <kbd className="kbd">ESC</kbd> Cancel
              </span>
            }
          />
        </div>

        <div className="mt-6 flex items-center justify-between">
          <span className="text-2xs font-mono text-surface-500">Combat is automatic — close range = engagement.</span>
          <button
            onClick={dismiss}
            className="btn-primary px-4 py-1.5"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}

function Row({ icon, title, body }: { icon: React.ReactNode; title: string; body: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="shrink-0 w-7 h-7 bg-surface-800 border border-surface-700 rounded flex items-center justify-center">
        {icon}
      </div>
      <div>
        <div className="text-xs font-mono font-semibold text-surface-100 mb-0.5">{title}</div>
        <div className="text-2xs font-mono text-surface-400 leading-relaxed">{body}</div>
      </div>
    </div>
  );
}
