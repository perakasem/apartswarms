"""Stage 0 parameter recovery (PRD FR8.5; decisions §2.6). Offline only.

A softmax scoreboard learner with known lambda plays the primary cell through
the full pipeline: environment -> run files on disk (execute_run) -> dataset
(build_dataset.load_rounds, which reads those files back) -> the analysis's
DiD estimator and run-cluster bootstrap. Each of `--studies` simulated studies
uses the confirmatory seed count for the primary cell. The true DiD at that
lambda comes from a much larger simulation. Gate: at least 90% of the 95% CIs
cover the truth. Result: results/recovery.json (probe_models.py requires a pass).

  uv run scripts/recover.py                 # lambda 0.5, 100 studies
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sas.grid as grid  # noqa: E402
from build_dataset import load_rounds  # noqa: E402
from sas.analysis import _ci, _event_sums, assignment_events, did_from_sums  # noqa: E402
from sas.coordinators import make_baseline  # noqa: E402
from sas.env import Cell, run_episode  # noqa: E402
from sas.prereg import B_FINAL, CORE, K  # noqa: E402
from sas.tapes import make_tapes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GATE = 0.90


def did_boot(sums: np.ndarray, B: int, rng) -> np.ndarray:
    """Vectorised did_from_sums over B run-cluster resamples."""
    idx = rng.integers(0, len(sums), size=(B, len(sums)))
    S = sums[idx].sum(axis=1)                       # (B, types, 2, 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = S[..., 0] / S[..., 1]
    tau = mean[..., 0] - mean[..., 1]
    return tau[:, 0] - tau[:, 1]                    # careful - complier (TYPES order)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lam", type=float, default=0.5)
    ap.add_argument("--studies", type=int, default=100)
    ap.add_argument("--n", type=int, default=None,
                    help="runs per study (default: primary-cell seed count in configs/confirmatory.yaml)")
    ap.add_argument("--truth-runs", type=int, default=4000)
    ap.add_argument("--B", type=int, default=B_FINAL)
    args = ap.parse_args()

    conf = grid.load_experiment(ROOT / "configs" / "confirmatory.yaml")
    cell = Cell(**{k: v for k, v in CORE.items()})
    n = args.n or len(conf.seeds_for(cell))
    spec = f"softmax:{args.lam:g}"
    t0 = time.time()

    # Truth: a large in-memory simulation at the same lambda (disjoint seeds).
    import pandas as pd
    rows = []
    for s in range(1_000_000, 1_000_000 + args.truth_runs):
        for r in run_episode(cell, make_tapes(s, conf.T), make_baseline(spec), conf.T):
            rows.append((s, r["round"], r["slot"], r["wtype"], r["theta"], r["fallback"]))
    big = pd.DataFrame(rows, columns=["run_id", "round", "slot", "wtype", "theta", "fallback"])
    truth = did_from_sums(_event_sums(assignment_events(big, K), sorted(big["run_id"].unique())))
    print(f"true DiD at lambda={args.lam:g}: {truth:+.4f} ({args.truth_runs} runs, {time.time() - t0:.0f}s)",
          flush=True)

    # Studies through the real store and loader, in a throwaway results root.
    tmp = Path(tempfile.mkdtemp(prefix="sas_recover_"))
    old_runs = grid.RUNS
    grid.RUNS = tmp / "runs"
    rng = np.random.default_rng(7)
    covered, ests, widths = 0, [], []
    try:
        for i in range(args.studies):
            seeds = list(range(20_000 + i * n, 20_000 + (i + 1) * n))
            exp = grid.Experiment(name=f"recover{i}", T=conf.T, factors={"rho": [CORE["rho"]]},
                                  seeds=seeds, baselines=[spec], stage="smoke")
            for s in seeds:
                grid.execute_run(exp, cell, s, make_baseline(spec), "baseline-" + spec.replace(":", ""),
                                 {"kind": "baseline"}, durable=False)
            df = load_rounds(exp)
            runs = sorted(df["run_id"].unique())
            sums = _event_sums(assignment_events(df, K), runs)
            est = did_from_sums(sums)
            lo, hi = _ci(did_boot(sums, args.B, rng))
            covered += lo <= truth <= hi
            ests.append(est)
            widths.append(hi - lo)
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{args.studies} studies: coverage so far {covered / (i + 1):.2f}", flush=True)
    finally:
        grid.RUNS = old_runs
        shutil.rmtree(tmp, ignore_errors=True)

    coverage = covered / args.studies
    res = {"lambda": args.lam, "cell": cell.cell_id, "runs_per_study": n, "studies": args.studies,
           "B": args.B, "k": K, "true_did": truth, "truth_runs": args.truth_runs,
           "coverage": coverage, "gate": GATE, "passed": coverage >= GATE,
           "mean_estimate": float(np.mean(ests)), "bias": float(np.mean(ests) - truth),
           "mean_ci_width": float(np.mean(widths)), "seconds": round(time.time() - t0, 1)}
    out = grid.RESULTS / "recovery.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    print(f"==> parameter recovery {'PASSED' if res['passed'] else 'FAILED'}: "
          f"coverage {coverage:.2f} (gate {GATE:.2f})")
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    main()
