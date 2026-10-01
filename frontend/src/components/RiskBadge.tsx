import { riskTone } from "../utils";

export function RiskBadge({ score }: { score: number }) {
  return (
    <span className={`inline-flex min-w-12 items-center justify-center rounded-full border px-2 py-1 text-xs font-bold tabular-nums ${riskTone(score)}`}>
      {score}
    </span>
  );
}
