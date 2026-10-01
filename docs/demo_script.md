# Five-Minute Demo Script

Before the demo, run the backend and frontend commands from `README.md`. Keep the
yellow **SYNTHETIC / SIMULATED DATA** label visible.

## 0:00-1:00 — Overview and queue

- Point out that every KPI was fetched from `/overview`.
- Show 12,000 transactions, graph scale, candidate rings, and active risks.
- Search for a ring/user and filter by risk/action.
- Open the highest-risk candidate.

## 1:00-2:00 — Emerging risk

- Use the risk-history chart and grounded checkpoint deltas.
- Explain that the planted emerging ring is detected on day 18, 12 days before
  the final day-30 checkpoint.
- Note that causal snapshots exclude future users and edges.

## 2:00-3:00 — Graph investigation

- Pan/zoom the Cytoscape graph and click a user/device/card.
- Show selection attributes and isolated neighborhood.
- Compare WHY FLAGGED with legitimate-sharing counter-evidence.
- Show the blast-radius user count and clearly labelled simulated exposure.

## 3:00-4:00 — Copilot and counterfactual

- Ask “Could this be legitimate?” and show the typed tool call result.
- Ask “What changed?” or “What is the blast radius?”
- Emphasize that no AI key is present and all claims follow tool evidence.
- Show the risk before/after removing one real shared entity.

## 4:00-5:00 — Simulator and decision

- Start with 9 accounts, 2 devices, 1 instrument, 3 transactions.
- Advance three steps. Watch graph size, risk, blast radius, and alert state grow.
- Add a note and choose Investigate or Confirm abuse; refresh to show persistence.
- Close with the measured limitation: combined evasion reduces recall to 0.4575,
  so RingGuard is an interpretable prototype, not a production fraud claim.
