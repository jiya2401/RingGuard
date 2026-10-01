import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { InvestigationPanel } from "./components/InvestigationPanel";
import { KpiGrid } from "./components/KpiGrid";
import { RiskQueue } from "./components/RiskQueue";
import { SimulatorPanel } from "./components/SimulatorPanel";
import type { InvestigationBundle, Overview, Ring } from "./types";
import { filterRings } from "./utils";

export default function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [rings, setRings] = useState<Ring[]>([]);
  const [selected, setSelected] = useState<Ring | null>(null);
  const [bundle, setBundle] = useState<InvestigationBundle | null>(null);
  const [query, setQuery] = useState("");
  const [minRisk, setMinRisk] = useState(0);
  const [action, setAction] = useState("");
  const [sort, setSort] = useState("risk_desc");
  const [loading, setLoading] = useState(true);
  const [investigationLoading, setInvestigationLoading] = useState(false);
  const [error, setError] = useState("");
  const selectedRingId = selected?.ring_id;

  const refresh = async () => {
    const [overviewData, queue] = await Promise.all([api.overview(), api.risks()]);
    setOverview(overviewData); setRings(queue.rings);
    setSelected((current) => current ? queue.rings.find((ring) => ring.ring_id === current.ring_id) ?? queue.rings[0] ?? null : queue.rings[0] ?? null);
  };

  useEffect(() => {
    setLoading(true); setError("");
    refresh().catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load RingGuard")).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedRingId) { setBundle(null); return; }
    let active = true;
    setInvestigationLoading(true);
    api.investigation(selectedRingId).then((data) => { if (active) setBundle(data); }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Unable to load investigation"); }).finally(() => { if (active) setInvestigationLoading(false); });
    return () => { active = false; };
  }, [selectedRingId]);

  const visible = useMemo(() => {
    const rows = filterRings(rings, query, minRisk, action);
    return [...rows].sort((a, b) => sort === "risk_asc" ? a.risk_score - b.risk_score : sort === "size_desc" ? b.size - a.size : b.risk_score - a.risk_score);
  }, [rings, query, minRisk, action, sort]);

  if (loading) return <FullState title="Building the intelligence view" detail="Loading the deterministic graph and scored risk queue…" />;
  if (error && !overview) return <FullState title="RingGuard API unavailable" detail={error} retry={() => window.location.reload()} />;

  return (
    <div className="relative min-h-screen">
      <header className="sticky top-0 z-40 border-b border-slate-800/90 bg-ink/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1680px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-xl border border-cyan/30 bg-cyan/10 text-lg text-cyan">◈</div><div><h1 className="font-semibold tracking-tight">RingGuard</h1><p className="text-[10px] uppercase tracking-[0.18em] text-slate-600">Coordinated abuse intelligence</p></div></div>
          <div className="flex items-center gap-3"><span className="hidden text-xs text-slate-600 sm:inline">Pipeline online · deterministic mode</span><span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[10px] font-bold tracking-wide text-amber-300">SYNTHETIC / SIMULATED DATA</span></div>
        </div>
      </header>

      <main className="mx-auto max-w-[1680px] space-y-5 px-4 py-5 sm:px-6">
        {error && <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">{error}<button className="ml-3 underline" onClick={() => setError("")}>Dismiss</button></div>}
        {overview && <KpiGrid overview={overview} />}
        <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_340px]">
          <section className="panel overflow-hidden">
            <div className="border-b border-slate-800 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="eyebrow">Risk queue</p><h2 className="mt-1 text-lg font-semibold">Prioritized investigations</h2></div><span className="text-xs text-slate-600">{visible.length} of {rings.length} candidates</span></div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4"><input className="control" placeholder="Search ring, pattern, user…" value={query} onChange={(event) => setQuery(event.target.value)} /><select className="control" value={minRisk} onChange={(event) => setMinRisk(Number(event.target.value))}><option value={0}>All risk levels</option><option value={25}>25+ Monitor</option><option value={45}>45+ Review</option><option value={65}>65+ Investigate</option><option value={80}>80+ Escalate</option></select><select className="control" value={action} onChange={(event) => setAction(event.target.value)}><option value="">All actions</option>{["MONITOR", "REVIEW", "INVESTIGATE", "ESCALATE", "DISMISS"].map((item) => <option key={item}>{item}</option>)}</select><select className="control" value={sort} onChange={(event) => setSort(event.target.value)}><option value="risk_desc">Risk high → low</option><option value="risk_asc">Risk low → high</option><option value="size_desc">Largest first</option></select></div>
            </div>
            <RiskQueue rings={visible} selectedId={selected?.ring_id} onSelect={setSelected} />
          </section>
          <SimulatorPanel onStart={async (controls) => { const state = await api.simulationStart(controls); await refresh(); return state; }} onStep={async () => { const state = await api.simulationStep(); await refresh(); return state; }} />
        </div>

        {selected ? investigationLoading || !bundle ? <section className="panel grid h-64 place-items-center text-sm text-slate-500">Recomputing investigation evidence…</section> : <InvestigationPanel ring={selected} bundle={bundle} onAction={async (nextAction, note) => { await api.action(selected.ring_id, nextAction, note); await refresh(); }} onCopilot={async (question) => (await api.copilot(selected.ring_id, question)).answer} /> : <section className="panel p-12 text-center text-sm text-slate-500">No risk candidates are available for investigation.</section>}
      </main>
    </div>
  );
}

function FullState({ title, detail, retry }: { title: string; detail: string; retry?: () => void }) { return <main className="grid min-h-screen place-items-center p-6"><section className="panel max-w-md p-8 text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl border border-cyan/30 bg-cyan/10 text-cyan">◈</div><h1 className="mt-5 text-xl font-semibold">{title}</h1><p className="mt-2 text-sm leading-6 text-slate-500">{detail}</p>{retry && <button className="btn btn-primary mt-5" onClick={retry}>Retry</button>}</section></main>; }
