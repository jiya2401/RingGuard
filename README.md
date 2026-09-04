# RingGuard

**AI Risk Manager for Coordinated Payment Abuse**
Razorpay Buildathon · Track 2

> "Risk isn't always visible in a transaction. Sometimes it's visible in the network around it."

## What this is

RingGuard asks **"Is the ecosystem around this transaction becoming risky?"** rather than
"Is this transaction risky?" — a graph-driven AI risk manager that detects, explains,
monitors, propagates, and prioritizes coordinated payment abuse using a heterogeneous
payment-ecosystem graph (users, devices, cards, UPI, IPs, merchants, mandates, sessions,
transactions) fused with temporal intelligence and behavioral signals.

## Status

Milestone-driven build. See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for the
full plan, audit findings, architecture, milestone gates, and evaluation protocol.

| Milestone | Status |
|---|---|
| M1 — Repository audit + scaffolding | ✅ Complete (plan, package skeleton, config, tests green) |

## Stack

- **Backend:** Python 3.14 · FastAPI · Pydantic v2 · NetworkX · scikit-learn · SQLite
- **Frontend (planned):** React · TypeScript · Vite · Tailwind · Cytoscape.js
- **Testing:** pytest + pytest-cov (backend) · Vitest (frontend, planned)

## Quick start (backend)

```bash
pip install -r requirements.txt
pytest
```

> **IMPORTANT:** This prototype uses **synthetic data only**. No real Razorpay
> transactions, accounts, devices, or monetary amounts are used or implied.
> All monetary values shown are clearly labelled SIMULATED DATA.