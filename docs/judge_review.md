# Judge-Style Technical Review

## Pass 1: biggest weaknesses

### 1. The best metric looks too good

Graph LR reached ROC-AUC 0.9957 on synthetic data. That can invite an invalid
production-quality claim. Fixes applied: forward-only split enforcement,
validation-only thresholds, an explicit H-archetype holdout, adversarial feature
dilution, and prominent limitations. The combined-evasion recall of 0.4575 is
reported beside the headline result.

### 2. Investigation requests could become too expensive

Early M8 replay copied a 12k-transaction graph once per ring/checkpoint and took
206 seconds. Exact checkpoint snapshots are now reused (53 seconds for the M8
demo fixture), the application service caches its scored graph, and the UI
limits counterfactual recomputation to the five most shared evidence entities.

### 3. A polished dashboard could conceal a parallel fake-data path

Fix applied: the frontend has no fallback metrics. KPIs, queue rows, Cytoscape
elements, timelines, history, evidence, blast radius, counterfactuals, simulator
state, and copilot answers all come from FastAPI backed by one
`RingGuardService`. Loading, empty, and error states are explicit.

## Pass 2: residual risks after fixes

- NetworkX and process-local state remain demo-scale choices.
- The simulator is deterministic and shares the risk pipeline, but its event
  state is not persisted.
- Action persistence is durable locally, but there is no production RBAC.
- Tests cover contracts and scripted E2E; browser rendering is verified by the
  production build rather than a cross-browser automation matrix.

These are documented limitations, not hidden failures. Replacing them would
require production infrastructure or real governed data, both intentionally out
of scope for this portfolio build.
