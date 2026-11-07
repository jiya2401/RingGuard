"""Run the swarm experiments over many seeds and save docs/swarm_results.json.

    python scripts/run_swarm_eval.py --train 10 --test 20
Every number in the report should come from this file.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.swarm.evaluate import evaluate, fit_models, group_rows  # noqa: E402
from backend.swarm.evasion import drop_events, rename_agents, tamper_agents  # noqa: E402
from backend.swarm.identity import apply_aliases, resolve_by_fingerprint  # noqa: E402
from backend.swarm.scenarios import generate_scenario  # noqa: E402


def rows_for(seeds, scen_kwargs=None, perturb=None, fp_coverage=None):
    rows = []
    for s in seeds:
        sc = generate_scenario(s, **(scen_kwargs or {}))
        ev, to_true = sc.events, {}
        if perturb:
            ev, to_true = perturb(sc.events, s)
        if fp_coverage is not None:
            m = resolve_by_fingerprint(ev, fp_coverage, s)
            ev = apply_aliases(ev, m)
            to_true = {canon: to_true.get(canon, canon) for canon in set(m.values())}
        rows += group_rows(ev, sc, to_true, seed=s)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=10)
    ap.add_argument("--test", type=int, default=20)
    ap.add_argument("--boot", type=int, default=300)
    a = ap.parse_args()
    train_seeds = range(0, a.train)
    test_seeds = range(1000, 1000 + a.test)          # disjoint from training seeds
    t0 = time.time()
    models = fit_models(rows_for(train_seeds))
    res: dict = {"train_seeds": a.train, "test_seeds": a.test, "conditions": {}}

    def run(name, **kw):
        res["conditions"][name] = evaluate(models, rows_for(test_seeds, **kw), n_boot=a.boot)
        print(f"[{time.time() - t0:5.0f}s] {name}", flush=True)

    run("clean")
    for p in (0.1, 0.25, 0.5):
        run(f"registry_missing_{p}", scen_kwargs={"registry_missing_prob": p})
    for p in (0.25, 0.5):
        run(f"covert_hijacks_declared_channel_{p}", scen_kwargs={"covert_on_sanctioned_prob": p})
    for k in (0.8, 0.5, 0.2):
        run(f"keep_events_{k}", perturb=lambda ev, s, k=k: (drop_events(ev, k, s), {}))
    for f in (0.07, 0.2):
        run(f"tamper_agents_{f}", perturb=lambda ev, s, f=f: (tamper_agents(ev, f, s), {}))
    for n in (3, 6.6):
        run(f"rename_{n}_names", perturb=lambda ev, s, n=n: rename_agents(ev, n, s))
    for c in (0.05, 0.2, 0.5, 1.0):
        run(f"rename_6.6_names_fingerprint_coverage_{c}",
            perturb=lambda ev, s: rename_agents(ev, 6.6, s), fp_coverage=c)

    out = Path("docs/swarm_results.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print("wrote", out)
    print(f"\n{'condition':44s} {'model':32s} AUROC  covertTPR  sanctFPR")
    for cond, d in res["conditions"].items():
        for m, v in d.items():
            if m.startswith("_"):
                continue
            print(f"{cond:44s} {m:32s} {v['auroc']['value']:.2f}   {v['covert_tpr']['value']:.2f}      {v['sanctioned_fpr']['value']:.2f}")


if __name__ == "__main__":
    main() 