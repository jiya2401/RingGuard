# RingGuard Architecture

RingGuard is a local-first fraud-intelligence prototype for coordinated payment
abuse. It uses only deterministic synthetic data; no real Razorpay records or
external AI credentials are required.

## Runtime flow

```text
Synthetic ecosystem
  -> heterogeneous NetworkX graph
  -> user coordination projection
  -> Louvain ring discovery
  -> structural + temporal + behavioral + money-flow risk
  -> legitimate-sharing deduction
  -> evidence, history, DNA, propagation, blast radius, counterfactuals
  -> typed investigation tools
  -> deterministic grounded copilot
  -> FastAPI
  -> React dashboard + Cytoscape investigation graph
```

The `RingGuardService` is the shared application boundary. API routes and tools
read the same cached `Ecosystem`, graph, and scored `Ring` objects. The frontend
does not carry fallback KPI values or fake ring payloads.

## Core packages

| Package | Responsibility |
|---|---|
| `backend/data` | deterministic generator, archetypes, hard negatives, SQLite actions |
| `backend/graph` | heterogeneous graph construction and schema |
| `backend/features` | user projection and graph features |
| `backend/detection` | deterministic Louvain candidate discovery |
| `backend/risk` | scoring, legitimacy, emerging history, propagation, counterfactuals, DNA |
| `backend/evaluation` | causal splits, metrics, robustness and hard-negative reports |
| `backend/models` | Logistic Regression and Random Forest comparators |
| `backend/agents` | typed tool registry and credential-free grounded assistant |
| `backend/api` | shared service, schemas, routes, CORS and health |
| `backend/simulation` | deterministic graph-growth attack simulator |
| `frontend` | React/Tailwind dashboard and Cytoscape investigation UI |

## Causality and leakage prevention

Transactions are sorted chronologically. Each graph-enhanced transaction row is
emitted before that transaction updates rolling user/device/instrument/IP state.
The split is strictly forward: simulated days `<21` train, `21..<25`
validation, and `25..30` test. Thresholds are chosen only on validation data.
Past graph snapshots preserve the declared observation window and remove future
users and edges.

## Grounding boundary

The copilot cannot query raw state directly. It calls a typed registry whose
results include provenance. The deterministic renderer then uses only those
returned fields. Optional future LLM adapters may rewrite phrasing, but must not
replace detection, scoring, evidence recomputation, or investigator safeguards.

## Persistence and simulation

Investigator actions and notes are stored in SQLite. Simulation is deliberately
ephemeral: each start resets to the original graph, and each step adds synthetic
users, shared devices/cards, transactions, and money-flow edges before rerunning
the production discovery and risk pipeline.

## Deployment shape

`compose.yaml` runs an independently health-checked FastAPI container and a
static Nginx frontend. Nginx proxies `/api` to the backend, so deployed browser
traffic can remain same-origin. SQLite lives on a named volume.
