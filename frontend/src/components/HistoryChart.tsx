import type { HistoryPoint } from "../types";

export function HistoryChart({ points }: { points: HistoryPoint[] }) {
  if (!points.length) return <p className="text-sm text-slate-500">No history is available.</p>;
  const width = 640, height = 190, pad = 28;
  const minDay = Math.min(...points.map((point) => point.day));
  const maxDay = Math.max(...points.map((point) => point.day));
  const x = (day: number) => pad + ((day - minDay) / Math.max(1, maxDay - minDay)) * (width - pad * 2);
  const y = (risk: number) => height - pad - (risk / 100) * (height - pad * 2);
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(point.day)},${y(point.risk)}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-48 w-full" role="img" aria-label="Risk history chart">
        {[25, 45, 65, 80].map((risk) => <g key={risk}><line x1={pad} x2={width - pad} y1={y(risk)} y2={y(risk)} stroke="#263247" strokeDasharray="4 4" /><text x={2} y={y(risk) + 4} fill="#64748b" fontSize="10">{risk}</text></g>)}
        <path d={path} fill="none" stroke="#4fd1c5" strokeWidth="3" />
        {points.map((point) => <g key={point.day}><circle cx={x(point.day)} cy={y(point.risk)} r="5" fill="#0b1220" stroke="#4fd1c5" strokeWidth="3" /><text x={x(point.day)} y={height - 6} textAnchor="middle" fill="#64748b" fontSize="9">d{point.day}</text></g>)}
      </svg>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {points.filter((point) => point.what_changed.length).slice(-4).map((point) => (
          <div key={point.day} className="rounded-lg border border-slate-800 bg-ink/50 p-3 text-xs">
            <p className="font-semibold text-cyan">Day {point.day} · risk {point.risk}</p>
            <p className="mt-1 text-slate-500">{point.what_changed.join(" · ")}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
