export type Driver = { layer: string; contribution: number; detail: string };
export type Signal = { signal: string; value: number; interpretation: string };

export type Ring = {
  ring_id: string;
  users: string[];
  structural_score: number;
  risk_score: number;
  confidence: number;
  size: number;
  primary_pattern: string;
  status: string;
  recommended_action: string;
  drivers: Driver[];
  risk_signals: Signal[];
  legitimate_signals: Signal[];
  affected_entities: Record<string, string[]>;
  dna?: { fingerprint: string; dominant_drivers: string[] };
};

export type Overview = {
  data_label: string;
  seed: number;
  transactions: number;
  entities: number;
  relationships: number;
  candidate_rings: number;
  active_risks: number;
  high_risks: number;
  simulated_value: number;
};

export type GraphPayload = {
  ring_id: string;
  nodes: Array<{ data: Record<string, unknown> & { id: string; entity_type?: string } }>;
  edges: Array<{ data: Record<string, unknown> & { id: string; source: string; target: string; rel_type?: string } }>;
  data_label: string;
};

export type HistoryPoint = {
  day: number;
  risk: number;
  base_risk: number;
  confidence: number;
  recommended_action: string;
  what_changed: string[];
  counters: Record<string, number>;
};

export type Evidence = {
  why_flagged: {
    risk_score: number;
    confidence: number;
    primary_pattern: string;
    primary_drivers: Array<{ layer: string; contribution: number; explanation: string }>;
    evidence: Array<{ signal: string; value: number; explanation: string }>;
    recommended_action: string;
  };
  why_not_fraud: {
    verdict: string;
    legitimacy_score: number;
    summary: string;
    counter_evidence: Array<{ signal: string; value: number; explanation: string }>;
  };
};

export type InvestigationBundle = {
  graph: GraphPayload;
  timeline: { ring_id: string; events: Array<Record<string, unknown>> };
  evidence: Evidence;
  history: { ring_id: string; history: HistoryPoint[] };
  blast: Record<string, unknown> & {
    counts: Record<string, number>;
    estimated_simulated_exposure: number;
    data_label: string;
  };
  counterfactual: {
    ring_id: string;
    counterfactuals: Array<{
      evidence_id: string;
      entity_type: string;
      before_risk: number;
      after_risk: number;
      risk_delta: number;
    }>;
  };
};
