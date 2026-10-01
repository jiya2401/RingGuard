# Limitations

1. **Synthetic-only validation.** Results demonstrate internal correctness and
   controlled separation, not live fraud performance or Razorpay readiness.
2. **High synthetic separability.** Graph LR ROC-AUC is 0.9957. The generator and
   detector intentionally share coordination semantics, so this should not be
   interpreted as real-world generalization.
3. **Evasion sensitivity.** Combined infrastructure dilution and timing smear
   reduce measured recall to 0.4575.
4. **In-memory graph.** NetworkX is appropriate for the 12k-transaction demo,
   not a high-throughput production payment graph. API state is single-process.
5. **Ephemeral simulation.** Simulator graph changes reset when the process or
   simulation restarts. Investigator actions persist; simulated events do not.
6. **SQLite concurrency.** SQLite is sufficient for a portfolio demo and one
   process. Multi-instance deployment needs a shared transactional datastore.
7. **Counterfactual scope.** The UI recomputes the five most widely shared
   evidence entities to keep response time modest; this is not an exhaustive
   causal model of human behavior.
8. **No learned calibration.** Risk scores are interpretable weighted evidence,
   not calibrated fraud probabilities.
9. **No external AI evaluation.** The default copilot is deterministic and safe,
   but its language flexibility is intentionally limited.
10. **No real authentication/RBAC.** Deployment files are demonstrative. Add
    identity, authorization, audit controls, TLS, rate limits, and managed
    secrets before any non-local use.
