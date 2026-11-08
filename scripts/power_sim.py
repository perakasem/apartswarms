"""Power by simulation (review 4.3 'Few workers'): how many runs per cell does
the DiD test need? Uses scoreboard learners whose true DiD is known to be
nonzero (softmax at several lambdas, and Bayes). For each n, draws many
n-run experiments from a large simulated pool and records how often the
95% run-cluster bootstrap CI excludes zero.

Also reports the minimum detectable effect (MDE, 80% power, two-sided 5%)
as 2.8 x the sampling SD of the pooled DiD, which is what bounds the
LLM-vs-Bayes gap (H3) we can detect, and TOST power at a true DiD of zero:
the share of replicates whose 90% CI, re-centred on zero, lies inside
+/- SESOI (review fix 1.4). If that is low, a null at that n is inconclusive.

  uv run scripts/power_sim.py --rho 0 --rho 1 --n 5 --n 10 --n 20 --n 30
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.analysis import _event_sums, assignment_events, did_from_sums  # noqa: E402
from sas.coordinators import make_baseline  # noqa: E402
from sas.env import Cell, run_episode  # noqa: E402
from sas.tapes import make_tapes  # noqa: E402


def pool_sums(spec: str, cell: Cell, T: int, n_pool: int, k: int) -> np.ndarray:
    rows = []
    for s in range(10_000, 10_000 + n_pool):   # disjoint from experiment seeds
        for r in run_episode(cell, make_tapes(s, T), make_baseline(spec), T):
            rows.append({"run_id": s, "round": r["round"], "slot": r["slot"],
                         "wtype": r["wtype"], "theta": r["theta"]})
    df = pd.DataFrame(rows)
    return _event_sums(assignment_events(df, k), sorted(df["run_id"].unique()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rho", type=float, action="append")
    ap.add_argument("--n", type=int, action="append", help="runs per cell to evaluate")
    ap.add_argument("--learner", action="append",
                    help="default: bayes, softmax:0.1, softmax:0.3, softmax:1")
    ap.add_argument("--T", type=int, default=60)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--pool", type=int, default=600)
    ap.add_argument("--reps", type=int, default=300)
    ap.add_argument("--B", type=int, default=300)
    ap.add_argument("--sesoi", type=float, default=0.05)
    ap.add_argument("--out", default="results/power_sim.csv")
    args = ap.parse_args()
    rhos = args.rho or [0.0, 1.0]
    ns = args.n or [10, 30, 60, 100, 150]
    learners = args.learner or ["bayes", "softmax:0.1", "softmax:0.3", "softmax:1"]
    rng = np.random.default_rng(0)

    rows = []
    for spec in learners:
        for rho in rhos:
            sums = pool_sums(spec, Cell(rho=rho), args.T, args.pool, args.k)
            true_did = did_from_sums(sums)
            for n in ns:
                est, hits, tost = [], 0, 0
                for _ in range(args.reps):
                    pick = rng.choice(len(sums), size=n, replace=False)
                    s = sums[pick]
                    d = did_from_sums(s)
                    boot = np.array([did_from_sums(s[rng.integers(0, n, n)]) for _ in range(args.B)])
                    boot = boot[np.isfinite(boot)]
                    lo, hi = np.quantile(boot, [0.025, 0.975])
                    hits += (lo > 0) or (hi < 0)
                    # TOST if the truth were 0: same sampling spread, centred on zero.
                    lo90, hi90 = np.quantile(boot - true_did, [0.05, 0.95])
                    tost += (lo90 > -args.sesoi) and (hi90 < args.sesoi)
                    est.append(d)
                sd = float(np.nanstd(est))
                rows.append({"learner": spec, "rho": rho, "n_runs": n, "true_did": true_did,
                             "power": hits / args.reps, "sd_did": sd, "mde_80": 2.8 * sd,
                             "tost_power_at_null": tost / args.reps})
                print(f"{spec:12s} rho={rho:g} n={n:3d}  DiD={true_did:+.3f}  "
                      f"power={hits / args.reps:.2f}  MDE80={2.8 * sd:.3f}  "
                      f"TOST@0={tost / args.reps:.2f}", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
