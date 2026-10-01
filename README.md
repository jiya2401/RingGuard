<div align="center">

# 🛡️ RingGuard

### Explainable graph intelligence for coordinated payment abuse

**Razorpay Buildathon · Track 2 portfolio project**

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-typed_API-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-TypeScript-61DAFB?logo=react&logoColor=111827)
![Data](https://img.shields.io/badge/data-100%25_synthetic-f59e0b)

> Risk is not always visible in a transaction. Sometimes it is visible in the
> network around it.

</div>

RingGuard builds a heterogeneous payment graph, discovers coordinated account
clusters, scores their structural/temporal/behavioral/money-flow evidence,
subtracts legitimate-sharing evidence, and gives an investigator one grounded
view of risk history, graph relationships, blast radius, counterfactuals, and
recommended actions.

**All data and monetary values are synthetic/simulated. RingGuard does not use
or imply access to real Razorpay data.**

## What is implemented

- Deterministic synthetic ecosystem with eight abuse archetypes and five classes
  of hard negatives.
- Causal heterogeneous NetworkX graph and deterministic Louvain ring discovery.
- Multi-layer interpretable risk plus explicit WHY FLAGGED / WHY NOT FRAUD.
- Observation-window-preserving risk history and emerging-ring detection.
- Leakage-free train/validation/test splits; Logistic Regression and Random
  Forest flat vs graph-enhanced comparisons.
- Precision, recall, F1, ROC-AUC, PR-AUC, FPR, precision@K, ring recall,
  emerging latency, hard-negative FPR, holdout, and adversarial evaluation.
- Risk propagation, two-hop blast radius, Ring DNA, and real evidence-removal
  counterfactual recomputation.
- Fourteen typed investigation tools and a deterministic grounded copilot that
  requires no external AI key.
- FastAPI endpoints for overview, queues, rings, graph, timeline, evidence,
  history, blast radius, counterfactuals, simulation, actions, and copilot.
- React + TypeScript + Vite + Tailwind dashboard with an interactive Cytoscape
  graph, filters, charts, evidence views, simulator, notes, and error states.
- Deterministic attack simulation through the production graph/risk pipeline.
- SQLite persistence for monitor, investigate, escalate, dismiss, mark
  legitimate, confirm abuse, and investigator notes.

## Measured seed-42 evaluation

| Model | Precision | Recall | F1 | ROC-AUC | PR-AUC | FPR |
|---|---:|---:|---:|---:|---:|---:|
| Flat Logistic Regression | 0.1824 | 1.0000 | 0.3085 | 0.8236 | 0.1651 | 0.2811 |
| Graph Logistic Regression | 0.8407 | 1.0000 | 0.9134 | 0.9957 | 0.9040 | 0.0119 |

The complete generated report is in
[`docs/evaluation_results.json`](docs/evaluation_results.json). The high graph
AUC is a synthetic benchmark result, not a production claim. Under combined
infrastructure dilution and timing smear, recall falls to **0.4575**; see
[`docs/evaluation.md`](docs/evaluation.md) and
[`docs/limitations.md`](docs/limitations.md).

## Windows local setup

Prerequisites: Python 3.14, Node 22, and Corepack/pnpm.

```powershell
git clone https://github.com/<your-username>/RingGuard.git
cd RingGuard

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd frontend
corepack enable
pnpm install
cd ..
```

Generate deterministic demo data and evaluation results:

```powershell
python scripts\generate_demo.py --seed 42 --out data\ecosystem.json
python scripts\run_evaluation.py --seed 42 --out docs\evaluation_results.json
```

Run the backend (terminal 1):

```powershell
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Run the frontend (terminal 2, from the repo root):

```powershell
cd frontend
pnpm run dev 
```

Open `http://localhost:5173`. API health is
`http://127.0.0.1:8000/health`; OpenAPI is
`http://127.0.0.1:8000/docs`.

## Verification

With the virtual environment activated:

```powershell
# Backend
python -m pytest
python -m compileall -q backend config scripts
python scripts\e2e_smoke.py --demo

# Frontend
cd frontend
pnpm run lint
pnpm run typecheck
pnpm run test
pnpm run build
```

Generated `data/`, `.venv/`, `node_modules/`, caches, SQLite databases, and
frontend `dist/` are gitignored.

## Architecture

```text
Synthetic events -> heterogeneous graph -> coordination projection
  -> ring discovery -> interpretable risk - legitimate-sharing deduction
  -> history / evidence / propagation / counterfactuals
  -> typed tools -> deterministic copilot -> FastAPI -> React/Cytoscape UI
```

See [`docs/architecture.md`](docs/architecture.md) for module and causality
details. `RINGGUARD_PROGRESS.md` is the handoff ledger for every milestone.

## Deployment preparation

No deployment or external account access is performed automatically. The repo
contains separate backend/frontend Dockerfiles plus `compose.yaml`:

```powershell
docker compose up --build
```

Then open `http://localhost:8080`. Full instructions and production caveats are
in [`docs/deployment.md`](docs/deployment.md).

## Demo and review material

- [`docs/demo_script.md`](docs/demo_script.md) — five-minute judge flow
- [`docs/judge_review.md`](docs/judge_review.md) — hostile self-review and fixes
- [`docs/evaluation.md`](docs/evaluation.md) — protocol and real results
- [`docs/limitations.md`](docs/limitations.md) — remaining constraints
- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — M1-M24 acceptance plan

RingGuard is a portfolio prototype for explainable investigation workflows, not
a production fraud decision system.
