import { describe, expect, it } from "vitest";
import { filterRings, formatCompact, riskTone } from "./utils";
import type { Ring } from "./types";

const ring = (id: string, risk: number, action: string): Ring => ({
  ring_id: id, users: ["U-1"], structural_score: 0.5, risk_score: risk,
  confidence: 80, size: 1, primary_pattern: "device reuse", status: "NEW",
  recommended_action: action, drivers: [], risk_signals: [], legitimate_signals: [],
  affected_entities: {},
});

describe("dashboard utilities", () => {
  it("filters the real ring list without synthesizing rows", () => {
    const rows = [ring("R-1", 70, "INVESTIGATE"), ring("R-2", 20, "DISMISS")];
    expect(filterRings(rows, "device", 45, "INVESTIGATE")).toEqual([rows[0]]);
    expect(filterRings(rows, "missing", 0, "")).toEqual([]);
  });

  it("formats metrics and assigns ordered risk tones", () => {
    expect(formatCompact(12_000)).toMatch(/12/);
    expect(riskTone(85)).toContain("rose");
    expect(riskTone(10)).toContain("slate");
  });
});
