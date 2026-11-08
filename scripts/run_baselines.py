"""Run the non-LLM baselines on the same cells and seeds (same tapes) as the
LLM runs. Offline and fast; resumable like run_experiment.py.

  uv run scripts/run_baselines.py --config configs/confirmatory.yaml
  uv run scripts/run_baselines.py --config configs/confirmatory.yaml --extra-seeds 200
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.coordinators import make_baseline  # noqa: E402
from sas.grid import execute_run, load_experiment, resolve_run  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--baseline", action="append", help="subset of config baselines")
    ap.add_argument("--extra-seeds", type=int, default=0,
                    help="also run this many seeds beyond the LLM seeds (baselines are free)")
    args = ap.parse_args()

    exp = load_experiment(args.config)
    n = 0
    for spec in args.baseline or exp.baselines:
        name = "baseline-" + spec.replace(":", "")
        for cell in exp.cells():
            seeds = list(exp.seeds_for(cell))
            if args.extra_seeds:
                # Extra seeds continue past the config's seeds but never enter
                # the reserved pilot range (or leave it, for a pilot config).
                lo, hi = (9000, 10000) if exp.role == "pilot" else (0, 9000)
                extra = [s for s in range(max(seeds) + 1, hi) if lo <= s][: args.extra_seeds]
                seeds += extra
            for seed in seeds:
                if resolve_run(exp, name, cell, seed) is not None:
                    continue
                execute_run(exp, cell, seed, make_baseline(spec), name,
                            {"kind": "baseline", "baseline": spec}, durable=False)
                n += 1
    print(f"{exp.name}: wrote {n} baseline runs")


if __name__ == "__main__":
    main()
