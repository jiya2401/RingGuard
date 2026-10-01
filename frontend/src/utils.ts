import type { Ring } from "./types";

export function formatCompact(value: number): string {
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function riskTone(score: number): string {
  if (score >= 80) return "text-rose-300 bg-rose-500/10 border-rose-500/30";
  if (score >= 65) return "text-orange-300 bg-orange-500/10 border-orange-500/30";
  if (score >= 45) return "text-amber-300 bg-amber-500/10 border-amber-500/30";
  if (score >= 25) return "text-sky-300 bg-sky-500/10 border-sky-500/30";
  return "text-slate-400 bg-slate-500/10 border-slate-500/30";
}

export function filterRings(rings: Ring[], query: string, minRisk: number, action: string): Ring[] {
  const needle = query.trim().toLowerCase();
  return rings.filter((ring) => {
    const matchesText = !needle || ring.ring_id.toLowerCase().includes(needle) ||
      ring.primary_pattern.toLowerCase().includes(needle) ||
      ring.users.some((user) => user.toLowerCase().includes(needle));
    return matchesText && ring.risk_score >= minRisk && (!action || ring.recommended_action === action);
  });
}
