import type { Overview } from "../types";
import { formatCompact } from "../utils";

type Kpi = { label: string; value: string; detail: string; accent: string };

export function KpiGrid({ overview }: { overview: Overview }) {
  const kpis: Kpi[] = [
    { label: "Active risks", value: String(overview.active_risks), detail: `${overview.high_risks} investigate+`, accent: "text-amber-300" },
    { label: "Candidate rings", value: String(overview.candidate_rings), detail: "Graph-discovered", accent: "text-cyan" },
    { label: "Transactions", value: formatCompact(overview.transactions), detail: `Seed ${overview.seed}`, accent: "text-sky-300" },
    { label: "Graph scale", value: formatCompact(overview.relationships), detail: `${formatCompact(overview.entities)} entities`, accent: "text-violet-300" },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {kpis.map((kpi) => (
        <section key={kpi.label} className="panel relative overflow-hidden p-4">
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-slate-600 to-transparent" />
          <p className="eyebrow">{kpi.label}</p>
          <p className={`mt-3 text-3xl font-semibold tracking-tight ${kpi.accent}`}>{kpi.value}</p>
          <p className="mt-1 text-xs text-slate-500">{kpi.detail}</p>
        </section>
      ))}
    </div>
  );
}
