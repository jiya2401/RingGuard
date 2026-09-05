# RingGuard — Implementation Plan

**Razorpay Buildathon · Track 2: AI Risk Manager for Coordinated Payment Abuse**

> "Risk isn't always visible in a transaction. Sometimes it's visible in the network around it."

---

## 1. Audit Findings (M1)

The repository at `c:\Users\Mr-A\RingGuard` was **empty** on inspection:

| Check | Result |
|---|---|
| Existing source code | **None** — greenfield build |
| Version control | **Not a git repository** (initialized during M1) |
| Existing tests / docs / data | **None** |
| Local Python | 3.14.2 present |
| Local Node | v22.16.0 / npm 11.4.2 present |
| Pre-installed backend deps | fastapi 0.136.3, uvicorn 0.48.0, pydantic 2.13.4, numpy 2.4.0, pandas 2.3.3, networkx 3.6.1, scipy 1.17.1, scikit-learn 1.8.0, pytest 9.0.3, httpx, pytest-cov, matplotlib |

**Implication:** nothing to preserve; every milestone is built from scratch on a
clean, verified toolchain. `requirements.txt` pins the versions confirmed to
work locally so the demo is reproducible.

---

## 2. Engineering Decisions & Rationale

| Decision | Choice | Why |
|---|---|---|
| Graph library | **NetworkX** (modular `backend/graph` layer) | Practical, testable, sufficient for demo scale; storage agnostic by design so Neo4j migration is a drop-in later. |
| State | **SQLite** via a thin storage module | Zero-config, deterministic, fast for demo data. |
| Baseline ML | scikit-learn: Logistic Regression + Random Forest (transaction-level) | Interpretable comparator. We must *prove* graph > flat features, not show off a black box. |
| Graph ML (Node2Vec/GNNs) | **Deferred** (spec §44) | Only adopt if it beats the interpretable graph system on ring detection and hard-negative robustness. Likely unnecessary. |
| API | FastAPI + Pydantic v2 typed schemas | Matches environment; typed contracts are a hard requirement. |
| Frontend | React + TypeScript + Vite + Tailwind | Standard, fast, professional. |
| Graph visualization | **Cytoscape.js** (managed directly from React) | Most robust interactive graph (zoom/pan/selection/neighborhood/ paths), designed for exactly this investigation UX. |
| AI Copilot | Tool-based agent with **structured grounding** | The "LLM" layer translates computed evidence into prose; it cannot fabricate evidence. If no API key is present in the demo env, run the copilot in deterministic tool-execution mode with template synthesis. |
| Randomness | `numpy.random.Generator` with fixed seed; zero ambient RNG | Deterministic reproduction of every experiment. |
| Time model | 30 simulated days | Training Days 1–21, validation 22–25, test 26–30 (spec §13). |

---

## 3. Target Architecture

```
                    RINGGUARD  AI RISK MANAGER
                                 |
                 +---------------+----------------+
                 |                                |
            TRANSACTION RISK                GRAPH RISK
                 |                                |
                 +---------------+----------------+
                                 |
                          TEMPORAL INTELLIGENCE
                                 |
                           BEHAVIORAL SIGNALS
                                 |
                          ABUSE-RING SENTINEL
                                 |
                         EMERGING RISK ENGINE
                                 |
                              RISK ENGINE
                                 |
                  +--------------+----------------+
                  |              |                |
              EXPLAIN        PROPAGATE        PREDICT
                  |              |                |
                 WHY?       BLAST RADIUS      WHAT NEXT?
                                 |
                           AI RISK COPILOT
                                 |
                            INVESTIGATOR
                                 |
                               ACTION
```

Backend modules (mirroring spec §41, adapted to this repo):

```
/backend
  /api          FastAPI app factory, routes, typed schemas
  /data         synthetic ecosystem generator, archetypes, hard negatives, storage
  /graph        schema, builder, graph-native metrics (storage-agnostic)
  /features     graph + temporal feature engineering
  /models       conventional baselines (transaction-level)
  /detection    ring discovery
  /risk         risk engine, temporal/emergent engine, propagation,
                blast radius, counterfactuals, ring DNA
  /agents       grounded copilot + tool registry
  /explanations WHY FLAGGED / WHY NOT FRAUD synthesis
  /evaluation   time-aware splits, metrics, generalization, adversarial
  /simulation   attack simulator + live event streaming
  /tests
/scripts        demo generation, evaluation, server bootstrap
/config         environment-driven settings
/docs           architecture + evaluation documentation
/frontend       React + TS + Vite + Tailwind + Cytoscape.js
```

---

## 4. Domain Model (v1)

**Node types (12):** `USER`, `DEVICE`, `CARD`, `BANK_ACCOUNT`, `UPI_ID`, `IP`,
`MERCHANT`, `PHONE`, `ADDRESS`, `MANDATE`, `SESSION`, `TRANSACTION`.

**Relationship types:** `USER_USED_DEVICE`, `USER_USED_IP`, `USER_OWNS_CARD`,
`USER_OWNS_BANK_ACCOUNT`, `USER_HAS_PHONE`, `USER_LIVES_AT_ADDRESS`,
`USER_PAID_MERCHANT`, `USER_SENT_TO_USER`, `USER_CREATED_SESSION`,
`USER_USED_UPI_ID`, `USER_HAS_MANDATE`, `USER_MADE_TRANSACTION`,
`TRANSACTION_AT_MERCHANT`, `TRANSACTION_USED_CARD`, `TRANSACTION_USED_UPI_ID`,
`TRANSACTION_USED_IP`, `TRANSACTION_FROM_USER`.

Every edge carries `source, target, rel_type, timestamp, weight, metadata`
and `transaction_id` where applicable.

**Risk layers (spec §11):**
`Individual + Relationship + Graph + Temporal + Behavioral + MoneyFlow − LegitimateSharing`
→ clamped 0–100 risk with named drivers and counter-signals.

---

## 5. Milestone Plan & Acceptance Criteria

Each milestone is **locked** until its verification gate passes: tests run
green (pytest), package imports cleanly, relevant artifacts/live servers run,
metrics are recorded, and docs are updated. Errors are never hidden.

| # | Milestone | Key deliverables | Exit gate |
|---|---|---|---|
| **M1** | Repository audit + scaffolding | Audit report (this doc), git init, `requirements.txt`, package skeleton, config | `python -c "import backend, config"` + `pytest --collect-only backend/tests` passes; structure committed |
| **M2** | Synthetic payment ecosystem | Deterministic generator: normal users, merchants, devices, cards, IPs, transactions + abuse archetypes A–H + hard negatives (household/office/campus/family card) + emerging ring; config-driven; every record traceable | Generated demo matches spec §46 scale tols; archetype counts verified by tests; determinism test (two runs → identical) |
| **M3** | Graph construction | Heterogeneous NetworkX graph from generated records; edge schema; storage-agnostic API (`build_graph`, `add_event`, `snapshot`) | Graph node/edge counts match generated records; edge attributes complete; unit tests |
| **M4** | Graph features | Spec §9 feature set: degree, k-core, PageRank, clustering, shared-device/card/IP counts, money-flow centrality, etc., each with semantic docstring | Feature values validated on toy graphs with expected monotonic behaviours |
| **M5** | Ring discovery | Candidate discovery: connected components → density/k-core filtering → temporal coordination scoring; candidate → structured Ring objects (spec §10) | Known planted rings recovered in tests (recall on planted rings ≥ 0.9 over 3 seeds) |
| **M6** | Risk engine | Multi-layer per-entity + per-ring risk with named drivers, legitimate-sharing subtraction, WHY FLAGGED rendering | Household ring scores below abuse-ring scores in tests; risk is deterministic and feature-derived |
| **M7** | Legitimate-sharing + hard negatives | Legitimate-sharing evidence extraction; counter-evidence (WHY NOT FRAUD); hard-negative benchmark set | Hard-negative FPR reported; abuse vs household separation asserted in tests  — **DONE**: evidence collector + 4-factor aggregation shared by engine and renderers; FPR reported at every action threshold with separation margin; WHY-FLAGGED/WHY-NOT-FRAUD renderers grounded in stored signals (graph-free fallback tested) |
| **M8** | Temporal + emerging-risk engine | Velocity/synchronization features at 5m/1h/24h/7d; emerging-risk trajectories with "what changed" deltas | Emerging ring detected **before** full ring materialises (latency quantified) |
| **M9** | Baseline + evaluation | Transaction-level LR/RF baseline; time-aware split (leakage-free); metrics suite: P/R/F1, ROC-AUC, PR-AUC, FPR, precision@K, ring detection, emerging-ring latency | Baseline evaluates under identical time split; metrics written to JSON; leakage prevention documented |
| **M10** | Generalization + adversarial | Unseen mixed ring archetypes (train on device/payment rings, test on mixed/emerging); adversarial hardening scenarios (1–10, spec §15) | Degradation vs. test-time variation quantified and documented, never hidden |
| **M11** | Propagation + blast radius | Risk propagation over graph edges (1st/2nd degree), affected-entity enumeration, simulated exposure (clearly labelled) | Propagation walks verified against planted edges in tests |
| **M12** | Counterfactual engine | "Without X" recomputation of real evidence (remove shared device → recompute graph+risk) | Values verified equal to a from-scratch recompute on reduced graph in tests |
| **M13** | AI Risk Manager tools | Typed tool registry: `get_ring_details`, `get_user_profile`, `get_connected_entities`, `get_transaction_timeline`, `get_shared_devices`, `get_shared_payment_instruments`, `get_money_flow`, `get_risk_features`, `get_legitimate_sharing_evidence`, `compare_with_baseline`, `calculate_blast_radius`, `get_similar_rings`, `get_risk_history`, `get_counterfactuals` | Every tool returns grounded, schema-validated results |
| **M14** | Grounded AI Risk Copilot | Agent orchestrates tool calls to answer "why", "could this be legitimate", "what changed", "blast radius", "what next"; no fabricated evidence; deterministic no-LLM fallback | Probe transcripts show tool calls preceding every data claim |
| **M15** | FastAPI backend | Spec §40 endpoints (/health, /overview, /risks, /rings, graph/timeline/evidence/blast-radius/risk-history/counterfactuals, /simulation/start+step, /investigation/action, /copilot/query) | `pytest` API tests green; `/health` live check |
| **M16** | Dashboard | RISK OVERVIEW KPIs + sortable RISK QUEUE (spec §32) from real computed data | Manual E2E: numbers match API truth |
| **M17** | Interactive graph + timeline | Investigation page: Cytoscape graph (zoom/pan/filter/highlight/neighborhood), timeline, evidence vs counter-evidence, ring DNA, blast radius, counterfactuals (spec §33–36) | Graph renders from API response; node click shows grounded details |
| **M18** | Attack simulator + live event mode | Interactive simulation controls producing visible graph evolution and risk escalation; streamed event ingestion (spec §29–30) | Simulating an attack changes dashboard + graph; alert fires at threshold |
| **M19** | Human-in-the-loop + feedback | Investigator actions (monitor/escalate/dismiss/mark legitimate/confirm/notes), statuses, feedback dataset + simulated loop (spec §27–28) | Action round-trips through API and persists; feedback file written |
| **M20** | UX polish | Enterprise styling, sorting, empty states, loading, error handling, demo-ready copy | Self-review against spec §51 |
| **M21** | End-to-end testing | Full-stack test: generate → detect → evaluate → serve → UI | Scripted E2E passes end to end |
| **M22** | Judge-style critique | Hostile self-review per spec §50; identify 3 biggest weaknesses; fix; re-test; repeat | Critique + fix log committed; metrics re-run |
| **M23** | README + architecture docs | README (demo flow, 5-minute script), architecture diagrams, evaluation report, leakage documentation | Docs match reality; no fabricated claims |
| **M24** | Final demo prep | Deterministic demo dataset baked in, 5-minute flow script, scripted demo server | Full 5-min flow rehearsed against live server |

**Ordering note (spec §52):** M2–M14 are backend science; M15 threads the API;
M16–M20 are product; M21–M24 harden and wrap. Frontend work must not begin
before the risk engine exists, so the UI is always backed by real data.

---

## 6. Evaluation & Leakage-Prevention Protocol

**Time-aware split (spec §13):** the generator stamps every entity and event
with a simulated time. We evaluate strictly forward:

| Split | Days | Purpose |
|---|---|---|
| Train | 1–21 | Fit baseline + choose risk thresholds |
| Validation | 22–25 | Hyper-parameter / threshold selection (explicitly never test) |
| Test | 26–30 | Final, reported metrics |

**Leakage rules (enforced structurally, not by convention):**
1. RingGuard features at time `t` are computed on a **graph truncated to
   `events ≤ t`** when timing matters (e.g., velocities, recency) — no future
   edges are ever visible to the scoring of a past snapshot.
2. Baseline transaction features use only columns available at slide time
   (no target-derived aggregates from the future).
3. Ring discovery for prediction at time `t` operates on the truncated graph.
4. A dedicated test (`tests/test_no_leakage.py`) asserts that a "future-tainted"
   snapshot and a "fair" snapshot differ and that the pipeline can run on a
   strictly causal snapshot.

**Credibility rule (spec §38):** if AUC approaches 1.0 we must raise overlap,
add noise, hard negatives, partial rings, and unseen structures until the
metric is credible — then report the *achieved* (not prettiest) numbers.

**Comparison contracts:** Baseline vs RingGuard share identical splits,
labels, and metric definitions. Reported metric set: precision, recall, F1,
ROC-AUC, PR-AUC, FPR, precision@K, ring detection rate, emerging-ring
detection rate, hard-negative FPR, detection latency (spec §12).

---

## 7. 5-Minute Judge Demo (spec §47)

1. **0–1 min · RISK OVERVIEW** — KPI cards from the live demo dataset
   (real counts, e.g., ~12k transactions, ~8k entities, ~25k relationships,
   3+ emerging risks), then open the RISK QUEUE sorted by risk.
2. **1–2 min · EMERGING RISK** — open an emerging cluster; show the LOW →
   MEDIUM → HIGH trajectory with the "what changed" deltas and why it crossed
   the threshold.
3. **2–3 min · GRAPH INVESTIGATION** — interactive graph: 9 accounts, 2
   devices, 1 payment instrument, 4 merchants; highlight suspicious edges
   (shared device + shared card + synchronized txns) **and** the
   legitimate-sharing counter-evidence.
4. **3–4 min · AI INVESTIGATION** — Copilot answers from grounded tool
   evidence: "why is this high?", "could this be a household?", "what changed
   the score?", "what is the blast radius?"
5. **4–5 min · ATTACK SIMULATOR** — raise accounts/shared devices/
   synchronization, SIMULATE ATTACK, watch the graph grow, ring form, risk
   escalate, alert fire, blast radius appear.

Closing line: *"A transaction-level system sees mostly individual events.
RingGuard sees the coordinated structure around them."*

---

## 8. Risk Register — What Can Go Wrong (checked every milestone)

| Risk | Mitigation |
|---|---|
| AUC hits 1.0 and looks fake | Spec §38 anti-credibility protocol; overlap/noise/hard-negative escalation |
| Graph is decoration, not detection | M5/M6 exit gates require ring recovery *from graph structure*; baseline comparison proves delta |
| Data leakage inflates metrics | Structural causality tests from §6, re-run at every evaluation milestone |
| Household sharing misclassified as crime | Hard-negative benchmark + legitimate-sharing evidence subtraction; M6 guarantee |
| LLM hallucinates evidence | Structured grounding (agents/grounding.py) + template fallback; tool-registry contract tests |
| Feature explosion / giant modules | Focused modules, semantic docstrings, shared feature registry |
| Demo fights flaky network | Everything computed server-side on demand; frontend caches nothing critical |

---

## 9. Definition of Done (spec §51)

Completed only when: Track 2 addressed; genuine heterogeneous graph used in
detection; synthetic generator with archetypes A–H and hard negatives;
legitimate-sharing reasoning; temporal + emerging-risk intelligence; ring
discovery; individual + ring risk; baseline-vs-graph evaluation with
time-aware leakage-free splits; generalization + adversarial testing; grounded
AI + tool-based copilot; WHY FLAGGED / WHY NOT FRAUD; real counterfactuals;
propagation + blast radius; ring DNA; risk history; recommendations; HITL +
feedback loop; interactive graph/timeline; attack simulator + live mode;
professional UI; automated tests; **no fabricated claims or metrics**; no
exposed secrets; strong README + architecture docs; deterministic demo dataset;
rehearsed 5-minute demo.

---

## 10. Final Product Statement

> RingGuard is an AI Risk Manager that detects coordinated payment abuse by
> understanding the network around transactions, tracks how risk evolves,
> explains the evidence, measures the potential blast radius, and helps
> investigators decide what to do next.

*All data in this prototype is synthetic. No real Razorpay transactions,
accounts, or amounts are used or implied anywhere.*