import { useState } from "react";
import type { InvestigationBundle, Ring } from "../types";
import { formatCompact } from "../utils";
import { GraphPanel } from "./GraphPanel";
import { HistoryChart } from "./HistoryChart";
import { RiskBadge } from "./RiskBadge";

type Props = {
  ring: Ring;
  bundle: InvestigationBundle;
  onAction: (action: string, note: string) => Promise<void>;
  onCopilot: (question: string) => Promise<string>;
};

export function InvestigationPanel({ ring, bundle, onAction, onCopilot }: Props) {
  const [note, setNote] = useState("");
  const [message, setMessage] = useState("");
  const [question, setQuestion] = useState("Why was this ring flagged?");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);

  const act = async (action: string) => {
    setBusy(true); setMessage("");
    try { await onAction(action, note); setMessage(`${action.replaceAll("_", " ")} saved`); setNote(""); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : "Action failed"); }
    finally { setBusy(false); }
  };
  const ask = async () => {
    setBusy(true);
    try { setAnswer(await onCopilot(question)); } catch (cause) { setAnswer(cause instanceof Error ? cause.message : "Copilot failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="eyebrow">Investigation · {ring.ring_id}</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">{ring.primary_pattern}</h2><p className="mt-2 font-mono text-[10px] text-slate-600">Ring DNA {ring.dna?.fingerprint ?? "—"}</p></div>
          <div className="flex items-center gap-3"><RiskBadge score={ring.risk_score} /><div><p className="text-xs font-semibold text-slate-300">{ring.recommended_action}</p><p className="text-[10px] text-slate-600">{ring.confidence}% confidence</p></div></div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <Metric label="Members" value={String(ring.size)} />
          <Metric label="Shared devices" value={String(ring.affected_entities.devices?.length ?? 0)} />
          <Metric label="Blast users" value={String(bundle.blast.counts.users ?? 0)} />
          <Metric label="Simulated exposure" value={`₹${formatCompact(bundle.blast.estimated_simulated_exposure)}`} />
        </div>
      </section>

      <GraphPanel graph={bundle.graph} />

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="panel p-5"><p className="eyebrow">Risk history</p><div className="mt-4"><HistoryChart points={bundle.history.history} /></div></section>
        <section className="panel p-5">
          <p className="eyebrow">Evidence balance</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <EvidenceList title="Why flagged" tone="text-rose-300" rows={bundle.evidence.why_flagged.evidence.map((item) => ({ name: item.signal, value: item.value, detail: item.explanation }))} />
            <EvidenceList title={`Counter-evidence · ${bundle.evidence.why_not_fraud.verdict}`} tone="text-emerald-300" rows={bundle.evidence.why_not_fraud.counter_evidence.map((item) => ({ name: item.signal, value: item.value, detail: item.explanation }))} />
          </div>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <section className="panel p-5 xl:col-span-2">
          <p className="eyebrow">Counterfactual recomputation</p>
          <div className="mt-4 overflow-auto">
            {bundle.counterfactual.counterfactuals.length ? <table className="w-full text-left text-xs"><thead className="text-slate-600"><tr><th className="pb-2">Remove evidence</th><th>Before</th><th>After</th><th>Δ risk</th></tr></thead><tbody className="divide-y divide-slate-800">{bundle.counterfactual.counterfactuals.map((row) => <tr key={row.evidence_id}><td className="py-3"><span className="text-slate-300">{row.evidence_id}</span><span className="ml-2 text-slate-600">{row.entity_type}</span></td><td>{row.before_risk}</td><td>{row.after_risk}</td><td className={row.risk_delta < 0 ? "text-emerald-300" : "text-amber-300"}>{row.risk_delta > 0 ? "+" : ""}{row.risk_delta}</td></tr>)}</tbody></table> : <p className="text-sm text-slate-500">No shared evidence is eligible for removal.</p>}
          </div>
        </section>
        <section className="panel p-5">
          <p className="eyebrow">Investigator decision</p>
          <textarea className="control mt-4 min-h-20 resize-y" placeholder="Add a grounded investigation note…" value={note} onChange={(event) => setNote(event.target.value)} />
          <div className="mt-3 grid grid-cols-2 gap-2">{["monitor", "investigate", "escalate", "dismiss", "mark_legitimate", "confirm_abuse"].map((action) => <button key={action} className={`btn ${action === "escalate" || action === "confirm_abuse" ? "btn-primary" : ""}`} disabled={busy} onClick={() => act(action)}>{action.replaceAll("_", " ")}</button>)}</div>
          {message && <p className="mt-3 text-xs text-cyan">{message}</p>}
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="panel p-5">
          <p className="eyebrow">Transaction timeline</p>
          <div className="mt-4 max-h-72 space-y-2 overflow-auto pr-2">{bundle.timeline.events.slice(-30).reverse().map((event, index) => <div key={`${String(event.timestamp)}-${index}`} className="flex gap-3 rounded-lg border border-slate-800 bg-ink/40 p-3 text-xs"><span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-cyan" /><div><p className="font-semibold text-slate-300">{String(event.type).toUpperCase()} · {String(event.entity)}</p><p className="mt-1 text-slate-600">{new Date(Number(event.timestamp) * 1000).toLocaleString()} {event.target ? `→ ${String(event.target)}` : ""}</p></div></div>)}</div>
        </section>
        <section className="panel p-5">
          <div className="flex items-start justify-between"><div><p className="eyebrow">Grounded copilot</p><h3 className="mt-1 font-semibold">Ask about this ring</h3></div><span className="rounded-full border border-cyan/30 bg-cyan/10 px-2 py-1 text-[10px] text-cyan">NO API KEY</span></div>
          <div className="mt-4 flex gap-2"><input className="control" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void ask(); }} /><button className="btn btn-primary" disabled={busy || !question.trim()} onClick={ask}>Ask</button></div>
          <div className="mt-4 min-h-32 rounded-xl border border-slate-800 bg-ink/60 p-4 text-sm leading-6 text-slate-400">{answer || "Answers are assembled only after typed tools return graph and risk evidence."}</div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-slate-800 bg-ink/50 p-3"><p className="eyebrow">{label}</p><p className="mt-2 text-lg font-semibold text-slate-200">{value}</p></div>; }
function EvidenceList({ title, tone, rows }: { title: string; tone: string; rows: Array<{ name: string; value: number; detail: string }> }) { return <div><h3 className={`text-sm font-semibold ${tone}`}>{title}</h3><div className="mt-3 space-y-3">{rows.map((row) => <div key={row.name} className="rounded-lg border border-slate-800 bg-ink/40 p-3"><div className="flex justify-between gap-2"><span className="text-xs font-semibold text-slate-300">{row.name.replaceAll("_", " ")}</span><span className="text-xs tabular-nums text-slate-500">{row.value}</span></div><p className="mt-1 text-[11px] leading-4 text-slate-600">{row.detail}</p></div>)}</div></div>; }
