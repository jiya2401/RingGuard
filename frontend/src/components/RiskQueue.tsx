import type { Ring } from "../types";
import { RiskBadge } from "./RiskBadge";

type Props = {
  rings: Ring[];
  selectedId?: string;
  onSelect: (ring: Ring) => void;
};

export function RiskQueue({ rings, selectedId, onSelect }: Props) {
  if (!rings.length) {
    return <div className="p-8 text-center text-sm text-slate-500">No rings match these filters.</div>;
  }
  return (
    <div className="max-h-[560px] overflow-auto">
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead className="sticky top-0 z-10 bg-panel text-[10px] uppercase tracking-[0.16em] text-slate-500">
          <tr>
            <th className="px-4 py-3 font-semibold">Risk</th>
            <th className="px-3 py-3 font-semibold">Candidate</th>
            <th className="px-3 py-3 font-semibold">Pattern</th>
            <th className="px-3 py-3 font-semibold">Members</th>
            <th className="px-3 py-3 font-semibold">Confidence</th>
            <th className="px-4 py-3 font-semibold">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/80">
          {rings.map((ring) => (
            <tr
              key={ring.ring_id}
              className={`cursor-pointer transition hover:bg-slate-800/60 ${selectedId === ring.ring_id ? "bg-cyan/5" : ""}`}
              onClick={() => onSelect(ring)}
            >
              <td className="px-4 py-3"><RiskBadge score={ring.risk_score} /></td>
              <td className="px-3 py-3">
                <p className="font-semibold text-slate-200">{ring.ring_id}</p>
                <p className="mt-1 font-mono text-[10px] text-slate-600">{ring.dna?.fingerprint ?? "—"}</p>
              </td>
              <td className="max-w-64 px-3 py-3 text-xs text-slate-400">{ring.primary_pattern}</td>
              <td className="px-3 py-3 tabular-nums text-slate-300">{ring.size}</td>
              <td className="px-3 py-3 tabular-nums text-slate-300">{ring.confidence}%</td>
              <td className="px-4 py-3 text-xs font-semibold text-slate-300">{ring.recommended_action}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
