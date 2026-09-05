<div align="center">

# 🛡️ RingGuard

### AI Risk Manager for Coordinated Payment Abuse 
 
**Razorpay Buildathon · Track 2** 
 
*"Risk isn't always visible in a transaction. Sometimes it's visible in the network around it."*
 
[![Status](https://img.shields.io/badge/status-milestone--driven%20build-blue)]()
[![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white)]()
[![Data](https://img.shields.io/badge/data-100%25%20synthetic-orange)]()
 
</div>

## 🧭 The core idea
 
Most fraud systems ask a narrow question:
 
> "Is *this* transaction risky?"
 
RingGuard asks a wider one:
 
> **"Is the ecosystem around this transaction becoming risky?"**
 
A single transaction can look perfectly clean in isolation — right amount, right merchant, right device — while quietly belonging to a **ring**: a cluster of users, devices, cards, UPI handles, IPs, mandates, and sessions that only look coordinated once you connect the dots.
 
```mermaid
graph LR
    U[👤 Users] --- G((Payment<br/>Ecosystem<br/>Graph))
    D[📱 Devices] --- G
    C[💳 Cards] --- G
    P[🏦 UPI Handles] --- G
    I[🌐 IPs] --- G
    M[🏪 Merchants] --- G
    N[📄 Mandates] --- G
    S[⏱️ Sessions] --- G
    T[💸 Transactions] --- G
    G --> R{Risk Signal}
    R -->|detect| A[🚨 Coordinated Abuse]
```
 
RingGuard **detects, explains, monitors, propagates, and prioritizes** risk across this heterogeneous graph, fused with temporal intelligence and behavioral signals.

## Status

Milestone-driven build. See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for the
full plan, audit findings, architecture, milestone gates, and evaluation protocol.

## 🚦 Build status
 
<details open>
<summary><b>Milestone tracker</b> — click to collapse</summary>

| # | Milestone | Status | Notes |
|---|-----------|:---:|---|
| M1 | Repository audit + scaffolding | ✅ | Plan, package skeleton, config, tests green |
| M2 | Synthetic payment ecosystem | ✅ | Archetypes A–H, hard negatives, demo generator (12k txns, 2s) |
| M3 | Graph construction | ✅ | Heterogeneous builder + schema, causal as_of snapshots |
| M4 | Graph features | ✅ | 21 semantics-validated features, coordination projection |
| M5 | Ring discovery | ✅ | Population-scaled fan-out cap + Louvain community discovery + coverage-based patterns + explainable structural score | 
| M6 | Risk engine | ✅ | 4-layer engine (structural/temporal/behavioral/money-flow) − legitimate-sharing deduction, WHY-FLAGGED drivers, recommendation tiers, causal `as_of` scoring |
| M7 | Legitimate-sharing + hard negatives | ✅ | ackend/risk/legitimacy.py (shared counter-evidence layer), ackend/evaluation/hard_negatives.py (FPR benchmark), ackend/explanations/why.py (WHY FLAGGED / WHY NOT FRAUD) |
| M8 | Temporal + emerging-risk engine | ⏳ | *Planned* |
| M9 | Baseline + evaluation | ⏳ | *Planned* |
| M10 | Generalization + adversarial | ⏳ | *Planned* |
| M11 | Propagation + blast radius | ⏳ | *Planned* |
| M12 | Counterfactual engine | ⏳ | *Planned* |
| M13 | AI Risk Manager tools | ⏳ | *Planned* |
| M14 | Grounded AI Risk Copilot | ⏳ | *Planned* |
| M15 | FastAPI backend | ⏳ | *Planned* |
| M16 | Dashboard | ⏳ | *Planned* |
| M17 | Interactive graph + timeline | ⏳ | *Planned* |
| M18 | Attack simulator + live events | ⏳ | *Planned* |
| M19 | HITL + feedback loop | ⏳ | *Planned* |
| M20 | UX polish | ⏳ | *Planned* |
| M21 | End-to-end testing | ⏳ | *Planned* |
| M22 | Judge-style critique | ⏳ | *Planned* |
| M23 | README + architecture docs | ⏳ | *Planned* |
| M24 | Final demo prep | ⏳ | *Planned* |


## Stack

- **Backend:** Python 3.14 · FastAPI · Pydantic v2 · NetworkX · scikit-learn · SQLite
- **Frontend (planned):** React · TypeScript · Vite · Tailwind · Cytoscape.js
- **Testing:** pytest + pytest-cov (backend) · Vitest (frontend, planned)

## Quick start (backend)

```bash
pip install -r requirements.txt
pytest
```

## ⚠️ Data & safety notice
 
> **This prototype uses SYNTHETIC DATA ONLY.**
> No real Razorpay transactions, accounts, devices, or monetary amounts are used or implied.
> All monetary values shown are clearly labelled **SIMULATED DATA**. 