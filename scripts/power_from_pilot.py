"""Power re-estimate from pilot LLM runs (2026-11-08, after the pilot gate).

scripts/power_sim.py sizes the confirmatory with simulated scoreboard
learners (Bayes, softmax), i.e. Bayes-like between-run variance. The pilot
showed LLM coordinators lock onto one worker for most of a run, so each run
is closer to one draw and the between-run spread is much larger. This script
takes the spread from the pilot runs themselves:

  * sd(n): SD of the pooled DiD over n runs, by resampling n of the 10 pilot
    runs with replacement (the DiD is a ratio of pooled sums, so this keeps
    the estimator exactly as analysed). An outer bootstrap over the 10-run
    pool gives a 10-90% range for sd(n): 10 runs estimate a variance poorly.
  * MDE80(n) = 2.8 sd(n); power at the Bayes-sized DiD (true DiD of the
    rho-uncertain Bayes learner over a large simulated pool);
    TOST power at a true DiD of 0 with SESOI 0.05 (normal approximation).
  * H3: SD of DiD_LLM - DiD_Bayes on paired seeds, resampled jointly.
  * H2: DiD(rho=1, n1) - DiD(rho=0, n0), the two cells resampled independently.
  * n80: runs per cell for 80% power at the Bayes-sized effect,
    n80 = n_pilot * (2.8 sd(n_pilot) / |effect|)^2.

Pilot cells are rho=0 and rho=1; rho=0.25 and 0.5 (confirmatory sweep only)
have no pilot LLM data and are not estimated here.

  uv run scripts/power_from_pilot.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sas.analysis import _event_sums, assignment_events, did_from_sums  # noqa: E402
from sas.env import Cell  # noqa: E402
from power_sim import pool_sums  # noqa: E402

MODELS = ["qwen3.5-397b", "deepseek-v4-flash", "glm-5.2"]
CONF_N = {0.0: 100, 1.0: 30}          # confirmatory runs per cell (configs/confirmatory.yaml)


def run_sums(rounds: pd.DataFrame, coord: str, rho: float, k: int) -> tuple[np.ndarray, list]:
    d = rounds[(rounds.coordinator == coord) & (rounds.rho == rho)]
    seeds = sorted(d.seed.unique())
    by_seed = {s: g.assign(run_id=s) for s, g in d.groupby("seed")}
    df = pd.concat([by_seed[s] for s in seeds])
    return _event_sums(assignment_events(df, k), seeds), seeds


def sd_at(sums: np.ndarray, n: int, rng, reps: int) -> float:
    est = [did_from_sums(sums[rng.integers(0, len(sums), n)]) for _ in range(reps)]
    return float(np.nanstd(est))


def sd_range(sums: np.ndarray, n: int, rng, reps: int, outer: int) -> tuple[float, float, float]:
    point = sd_at(sums, n, rng, reps)
    outer_sd = []
    for _ in range(outer):
        pool = sums[rng.integers(0, len(sums), len(sums))]
        outer_sd.append(sd_at(pool, n, rng, reps // 4))
    lo, hi = np.nanquantile(outer_sd, [0.1, 0.9])
    return point, float(lo), float(hi)


def power(effect: float, sd: float) -> float:
    z = abs(effect) / sd
    return float(norm.cdf(z - 1.96) + norm.cdf(-z - 1.96))


def tost(sd: float, sesoi: float = 0.05) -> float:
    """P(90% CI inside +/- sesoi | true 0), normal approximation."""
    half = 1.645 * sd
    if half >= sesoi:
        return 0.0
    return float(2 * norm.cdf((sesoi - half) / sd) - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", default=str(ROOT / "results/pilot/data/rounds.csv.gz"))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--outer", type=int, default=200)
    ap.add_argument("--pool", type=int, default=600, help="simulated Bayes runs for the true Bayes DiD")
    ap.add_argument("--out", default=str(ROOT / "results/power_from_pilot.json"))
    args = ap.parse_args()
    rng = np.random.default_rng(0)
    rounds = pd.read_csv(args.rounds)

    bayes_true = {rho: did_from_sums(pool_sums("bayes", Cell(rho=rho), 60, args.pool, args.k))
                  for rho in CONF_N}
    print("Bayes-sized DiD (rho-uncertain Bayes, simulated pool of %d): " % args.pool
          + ", ".join(f"rho={r:g}: {v:+.3f}" for r, v in bayes_true.items()))

    out = {"bayes_true_did": {str(r): v for r, v in bayes_true.items()}, "models": {}}
    bayes_sums = {rho: run_sums(rounds, "baseline-bayes", rho, args.k) for rho in CONF_N}
    rows = []
    for coord in ["baseline-bayes"] + MODELS:
        res = {}
        for rho, n_conf in CONF_N.items():
            sums, seeds = run_sums(rounds, coord, rho, args.k)
            n0 = len(sums)
            sd10, _, _ = sd_range(sums, n0, rng, args.reps, 1)
            sdn, lo, hi = sd_range(sums, n_conf, rng, args.reps, args.outer)
            eff = bayes_true[rho]
            n80 = n0 * (2.8 * sd10 / abs(eff)) ** 2
            r = {"pilot_did": did_from_sums(sums), "n_conf": n_conf, "sd": sdn, "sd_lo": lo, "sd_hi": hi,
                 "mde80": 2.8 * sdn, "power_at_bayes_effect": power(eff, sdn),
                 "power_lo": power(eff, hi), "power_hi": power(eff, lo),
                 "tost_at_null": tost(sdn), "n80": n80}
            if coord != "baseline-bayes":
                bs, bseeds = bayes_sums[rho]
                assert bseeds == seeds, "LLM and Bayes pilot seeds differ"
                gaps = []
                for _ in range(args.reps):
                    pick = rng.integers(0, n0, n_conf)
                    gaps.append(did_from_sums(sums[pick]) - did_from_sums(bs[pick]))
                r["h3_sd"] = float(np.nanstd(gaps))
                r["h3_mde80"] = 2.8 * r["h3_sd"]
            res[str(rho)] = r
            rows.append((coord, rho, r))
        # H2 contrast: rho=1 at its n minus rho=0 at its n, independent cells.
        s0, _ = run_sums(rounds, coord, 0.0, args.k)
        s1, _ = run_sums(rounds, coord, 1.0, args.k)
        h2 = [did_from_sums(s1[rng.integers(0, len(s1), CONF_N[1.0])])
              - did_from_sums(s0[rng.integers(0, len(s0), CONF_N[0.0])]) for _ in range(args.reps)]
        h2_eff = bayes_true[1.0] - bayes_true[0.0]
        h2_sd = float(np.nanstd(h2))
        res["h2"] = {"sd": h2_sd, "mde80": 2.8 * h2_sd, "bayes_effect": h2_eff, "power_at_bayes_effect": power(h2_eff, h2_sd)}
        out["models"][coord] = res

    print("\nH1 (DiD != 0) at confirmatory n; power at the Bayes-sized DiD. sd range = 10-90% over pilot pools.")
    print(f"{'coordinator':20s} {'rho':>4s} {'n':>4s} {'pilot DiD':>10s} {'sd(n)':>7s} {'sd range':>15s} "
          f"{'MDE80':>6s} {'power':>6s} {'power range':>12s} {'TOST@0':>6s} {'n for 80%':>9s}")
    for coord, rho, r in rows:
        print(f"{coord:20s} {rho:4g} {r['n_conf']:4d} {r['pilot_did']:+10.3f} {r['sd']:7.3f} "
              f"[{r['sd_lo']:.3f}, {r['sd_hi']:.3f}] {r['mde80']:6.3f} {r['power_at_bayes_effect']:6.2f} "
              f"[{r['power_lo']:.2f}, {r['power_hi']:.2f}] {r['tost_at_null']:6.2f} {r['n80']:9.0f}")
    print("\nH3 (LLM - Bayes, paired seeds) and H2 (DiD(rho=1) - DiD(rho=0)) at confirmatory n:")
    for coord in MODELS:
        m = out["models"][coord]
        print(f"{coord:20s} H3 MDE80 rho=0: {m['0.0']['h3_mde80']:.3f}, rho=1: {m['1.0']['h3_mde80']:.3f}; "
              f"H2 MDE80 {m['h2']['mde80']:.3f}, power at Bayes contrast {m['h2']['bayes_effect']:+.3f}: "
              f"{m['h2']['power_at_bayes_effect']:.2f}")
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
