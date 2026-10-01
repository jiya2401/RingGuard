## Baseline audit

- Status: complete.
- Files involved: all existing source, tests, scripts, configuration,
  documentation, `.gitignore`, ignored demo-data manifest, current `git status`,
  current `git diff`, and saved `_*.txt` diagnostics.
- Existing functionality: M1-M7 are implemented; M8 is partially implemented.
- Tests executed: saved diagnostics reviewed; a fresh environment run follows.
- Failures remaining: M8 snapshot metadata, inspection schema, emerging-ring
  coverage/lead time, and demo-scale background mega-component.
- Next task: reproduce the M8 failures in `.venv`, then stabilize M8.

## M8 - Temporal and emerging risk

- Status: complete.
- Files involved: `backend/risk/emerging.py`, `backend/detection/rings.py`,
  `backend/graph/builder.py`, `backend/data/generator.py`,
  `scripts/inspect_m8.py`, `backend/tests/test_m8_emerging.py`.
- Functionality implemented: observation-window metadata is preserved through
  causal snapshots; exact checkpoint snapshots are reused for practical demo
  performance; accumulating structural growth cannot present as a risk reversal;
  the current report schema is supported by `scripts/inspect_m8.py`; planted
  emerging-ring lead time and the background-component cap are regression-tested.
- Tests executed: `test_m5_rings.py` + `test_m8_emerging.py` (29 passed); complete
  inherited backend suite (155 passed, 2 skipped). M8 demo fixture improved from
  206.42s to 53.19s on this machine.
- Failures remaining: none for the M8 gate.
- Next task: implement M9-M12.

## M9-M12 - Evaluation and graph reasoning

- Status: complete.
- Files involved: `backend/evaluation/splits.py`, `backend/evaluation/metrics.py`,
  `backend/models/baselines.py`, `backend/risk/propagation.py`,
  `backend/risk/counterfactual.py`, `backend/risk/dna.py`,
  `scripts/run_evaluation.py`, `docs/evaluation_results.json`, and M9-M12 tests.
- Functionality implemented: strict train/validation/test event-time splits;
  causal pre-event graph features; Logistic Regression and Random Forest flat
  baselines plus graph-enhanced comparators; validation-only threshold choice;
  precision/recall/F1/ROC-AUC/PR-AUC/FPR/precision@K; ring recall, emerging
  latency, hard-negative FPR; held-out-archetype and deterministic adversarial
  evaluation; bounded risk propagation; blast radius with simulated exposure;
  from-scratch counterfactual recomputation; stable Ring DNA.
- Tests executed: 9 focused M9-M12 tests; complete backend suite (164 passed,
  2 skipped); syntax compilation; `git diff --check`.
- Reproducible seed-42 results: baseline LR F1 0.3085 / PR-AUC 0.1651;
  graph-enhanced LR F1 0.9134 / PR-AUC 0.9040; ring recall 1.0 (5/5);
  emerging lead 12 days; combined evasion recall 0.4575 (documented weakness).
- Failures remaining: none for the M9-M12 gates.
- Next task: implement M13-M15 tools, deterministic copilot, and FastAPI.

## M13-M15 - Tools, copilot, and API

- Status: complete.
- Files involved: `backend/agents/tools.py`, `backend/agents/copilot.py`,
  `backend/api/service.py`, `backend/api/schemas.py`, `backend/api/app.py`,
  `backend/data/storage.py`, `backend/simulation/engine.py`, and API tests.
- Functionality implemented: 14 typed investigation tools with provenance;
  deterministic credential-free grounded copilot; shared application service;
  typed FastAPI schemas; health, overview, risks, rings, user, graph, timeline,
  evidence, history, blast-radius, counterfactual, simulation, investigation,
  tools, and copilot endpoints; configurable CORS; SQLite-backed actions.
- Tests executed: 8 focused tool/copilot/API tests; complete backend suite green;
  syntax compilation; `git diff --check`; real Uvicorn `/health` smoke check.
- Failures remaining: none for M13-M15.
- Next task: build the React/TypeScript/Tailwind/Cytoscape frontend against these
  real API contracts.

## M16-M17 - Frontend dashboard and investigation UI

- Status: complete.
- Files involved: `frontend/` React/TypeScript/Vite/Tailwind/Cytoscape project.
- Functionality implemented: responsive fraud-intelligence dashboard; real KPI
  overview; searchable/filterable/sortable risk queue; Cytoscape neighborhood
  graph with node/edge details; transaction timeline; causal risk-history chart;
  evidence/counter-evidence; blast radius; counterfactual table; actions/notes;
  grounded copilot; loading/empty/error states; persistent synthetic-data labels.
- Tests executed: ESLint clean; strict TypeScript check green; 2 Vitest tests
  pass; Vite production build green with split React/Cytoscape chunks.
- Failures remaining: none for M16-M17.
- Next task: full-stack E2E and final UX review.

## M18-M19 - Simulator and investigator persistence

- Status: complete.
- Files involved: `backend/simulation/engine.py`, `backend/data/storage.py`, API
  service/routes, simulator dashboard panel, and M18-M19 tests.
- Functionality implemented: deterministic controls for accounts, shared devices,
  instruments, and coordinated transactions; graph growth through the production
  detector/risk engine; risk escalation, alerting, and blast-radius changes;
  monitor/investigate/escalate/dismiss/mark-legitimate/confirm-abuse actions;
  notes and SQLite persistence.
- Tests executed: 9 focused simulator/persistence tests plus API integration and
  the complete backend suite.
- Failures remaining: none for M18-M19.
- Next task: M20-M24 polish, E2E, critique, docs, and deployment prep.

## M20-M24 - Polish, E2E, review, docs, and deployment prep

- Status: not started.
- Files involved: `README.md`, `IMPLEMENTATION_PLAN.md`, new documentation,
  deployment files, and full-stack tests.
- Functionality implemented: original plan and M5/M7 findings documentation.
- Tests executed: none for these milestones.
- Failures remaining: all milestone deliverables.
- Next task: complete after product functionality is implemented.
