import type { GraphPayload, InvestigationBundle, Overview, Ring } from "./types";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  overview: () => request<Overview>("/overview"),
  risks: () => request<{ total: number; rings: Ring[] }>("/risks?sort=risk_desc"),
  investigation: async (ringId: string): Promise<InvestigationBundle> => {
    const encoded = encodeURIComponent(ringId);
    const [graph, timeline, evidence, history, blast, counterfactual] = await Promise.all([
      request<GraphPayload>(`/rings/${encoded}/graph`),
      request<InvestigationBundle["timeline"]>(`/rings/${encoded}/timeline`),
      request<InvestigationBundle["evidence"]>(`/rings/${encoded}/evidence`),
      request<InvestigationBundle["history"]>(`/rings/${encoded}/history`),
      request<InvestigationBundle["blast"]>(`/rings/${encoded}/blast-radius`),
      request<InvestigationBundle["counterfactual"]>(`/rings/${encoded}/counterfactual`),
    ]);
    return { graph, timeline, evidence, history, blast, counterfactual };
  },
  action: (ringId: string, action: string, note: string) =>
    request<Record<string, unknown>>("/investigation/action", {
      method: "POST",
      body: JSON.stringify({ ring_id: ringId, action, note }),
    }),
  simulationStart: (controls: Record<string, number>) =>
    request<Record<string, unknown>>("/simulation/start", { method: "POST", body: JSON.stringify(controls) }),
  simulationStep: () => request<Record<string, unknown>>("/simulation/step", { method: "POST" }),
  copilot: (ringId: string, question: string) =>
    request<{ answer: string; tool_calls: Array<{ tool: string }>; data_label: string }>("/copilot/query", {
      method: "POST",
      body: JSON.stringify({ ring_id: ringId, question }),
    }),
};
