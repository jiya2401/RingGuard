import { useState } from "react";

type Props = {
  onStart: (controls: Record<string, number>) => Promise<Record<string, unknown>>;
  onStep: () => Promise<Record<string, unknown>>;
};

export function SimulatorPanel({ onStart, onStep }: Props) {
  const [controls, setControls] = useState({ accounts: 9, shared_devices: 2, shared_instruments: 1, coordinated_transactions: 3 });
  const [state, setState] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const change = (key: keyof typeof controls, value: number) => setControls((current) => ({ ...current, [key]: value }));
  const run = async (operation: () => Promise<Record<string, unknown>>) => {
    setBusy(true); setError("");
    try { setState(await operation()); } catch (cause) { setError(cause instanceof Error ? cause.message : "Simulation failed"); }
    finally { setBusy(false); }
  };
  return (
    <section className="panel p-4">
      <div className="flex items-start justify-between gap-4">
        <div><p className="eyebrow">Attack simulator</p><h2 className="mt-1 text-lg font-semibold">Grow a coordinated cluster</h2></div>
        <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-1 text-[10px] font-semibold text-violet-300">DETERMINISTIC</span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        {Object.entries(controls).map(([key, value]) => (
          <label key={key} className="label capitalize">{key.replaceAll("_", " ")}
            <input className="control mt-1" type="number" min={1} value={value} onChange={(event) => change(key as keyof typeof controls, Number(event.target.value))} />
          </label>
        ))}
      </div>
      <div className="mt-4 flex gap-2">
        <button className="btn btn-primary" disabled={busy} onClick={() => run(() => onStart(controls))}>Start attack</button>
        <button className="btn" disabled={busy || !state || state.complete === true} onClick={() => run(onStep)}>Advance step</button>
      </div>
      {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}
      {state && (
        <div className="mt-4 rounded-xl border border-slate-800 bg-ink/60 p-3 text-xs text-slate-400">
          <div className="flex justify-between"><span>Step {String(state.step)}</span><span>{Array.isArray(state.simulated_users) ? state.simulated_users.length : 0} accounts</span></div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full bg-cyan transition-all" style={{ width: `${Math.min(100, ((Array.isArray(state.simulated_users) ? state.simulated_users.length : 0) / controls.accounts) * 100)}%` }} /></div>
          <p className={`mt-3 font-semibold ${state.alert_triggered ? "text-rose-300" : "text-slate-500"}`}>{state.alert_triggered ? "Alert threshold crossed" : "No alert yet"}</p>
          <p className="mt-1 text-slate-600">SIMULATED ATTACK / SYNTHETIC DATA</p>
        </div>
      )}
    </section>
  );
}
