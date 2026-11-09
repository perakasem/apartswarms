"""POST-HOC, EXPLORATORY analyses of the confirmatory data (DEVIATIONS G29).
Decided after the confirmatory results were read; none of this enters the
confirmatory family, and none of it may be reported as a preregistered test.

  1. H3 equivalence (TOST): 90% paired-seed bootstrap CI of DiD_LLM - DiD_Bayes
     (rho-uncertain Bayes, the H3 comparator) in the primary cell, against
     +/-0.05 (the SESOI the preregistration fixed for H1 only). Same estimator,
     pairing, k and bootstrap as sas.analysis.paired_did_gap.
  2. Achieved H1 power: from the confirmatory bootstrap SE of the DiD, power
     against the Bayes-sized DiD (normal approximation).
  3. Position bias: per-coordinator primacy (share of choices at list position
     1 minus 1/8, run-bootstrap CI), and a simulation check of the softmax
     baseline's position flag on 2,000 fresh seeds (disjoint from every
     experiment seed) to see whether it is a property of the baseline code.

  uv run scripts/exploratory_posthoc.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chisquare, norm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sas.analysis import _event_sums, assignment_events, did_from_sums  # noqa: E402
from sas.coordinators import make_baseline  # noqa: E402
from sas.env import Cell, run_episode  # noqa: E402
from sas.prereg import H3_COMPARATOR, K, SESOI  # noqa: E402
from sas.tapes import make_tapes  # noqa: E402

DATA = ROOT / "results/confirmatory/data/rounds.csv.gz"
OUT = ROOT / "results/confirmatory/exploratory"
MODELS = ["qwen3.5-397b", "deepseek-v4-flash", "glm-5.2"]
PRIMARY = "rho0_fb-outcome_c5_pi0.25"
B = 5000


def paired_sums(df, coord_a, coord_b, cell):
    a = df[(df.coordinator == coord_a) & (df.cell_id == cell)]
    b = df[(df.coordinator == coord_b) & (df.cell_id == cell)]
    common = sorted(set(a.seed) & set(b.seed))
    a, b = a[a.seed.isin(common)], b[b.seed.isin(common)]
    ra = a.groupby("seed")["run_id"].first().reindex(common).tolist()
    rb = b.groupby("seed")["run_id"].first().reindex(common).tolist()
    return _event_sums(assignment_events(a, K), ra), _event_sums(assignment_events(b, K), rb), len(common)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA, dtype={"notes": str, "raw": str, "served_model": str}, low_memory=False)
    rng = np.random.default_rng(0)
    out = {"note": "POST-HOC, EXPLORATORY (DEVIATIONS G29). Not part of the confirmatory family.",
           "sesoi": SESOI, "k": K, "B": B}

    # 1. H3 TOST
    tost = []
    for m in MODELS:
        sa, sb, n = paired_sums(df, m, H3_COMPARATOR, PRIMARY)
        idx = rng.integers(0, n, size=(B, n))
        boot = np.array([did_from_sums(sa[i]) - did_from_sums(sb[i]) for i in idx])
        gap = did_from_sums(sa) - did_from_sums(sb)
        lo90, hi90 = np.quantile(boot, [0.05, 0.95])
        lo95, hi95 = np.quantile(boot, [0.025, 0.975])
        tost.append({"coordinator": m, "n_seeds": n, "gap": gap, "ci95_lo": lo95, "ci95_hi": hi95,
                     "ci90_lo": lo90, "ci90_hi": hi90,
                     "equivalent_within_sesoi": bool(lo90 > -SESOI and hi90 < SESOI)})
    out["h3_tost"] = tost

    # 2. Achieved H1 power vs the Bayes-sized DiD in the primary cell
    s = pd.read_csv(ROOT / "results/confirmatory/analysis/summary.csv")
    bayes = s[(s.coordinator == H3_COMPARATOR) & (s.cell_id == PRIMARY)].iloc[0]
    power = []
    for m in MODELS:
        r = s[(s.coordinator == m) & (s.cell_id == PRIMARY)].iloc[0]
        se = (r.did_hi - r.did_lo) / (2 * 1.96)
        z = abs(bayes.did) / se
        power.append({"coordinator": m, "n_runs": int(r.n_runs), "did_se": se, "bayes_did": float(bayes.did),
                      "power_at_bayes_did": float(norm.cdf(z - 1.96) + norm.cdf(-z - 1.96))})
    out["achieved_h1_power"] = power

    # 3a. Primacy per coordinator (deduplicated as in sas.analysis.position_bias)
    d = df.drop_duplicates(["coordinator", "seed", "round", "label", "position"])
    prim = []
    for c, g in d.groupby("coordinator"):
        per_run = g.groupby("run_id")["position"].apply(lambda x: (x == 0).mean()).to_numpy()
        bt = per_run[rng.integers(0, len(per_run), (B, len(per_run)))].mean(1)
        counts = np.bincount(g["position"].astype(int), minlength=8)
        prim.append({"coordinator": c, "pos1_share": float((g["position"] == 0).mean()),
                     "pos1_minus_uniform": float((g["position"] == 0).mean() - 1 / 8),
                     "ci95_lo": float(np.quantile(bt, 0.025) - 1 / 8), "ci95_hi": float(np.quantile(bt, 0.975) - 1 / 8),
                     "chi2_p": float(chisquare(counts).pvalue),
                     **{f"pos{i + 1}": float(v / counts.sum()) for i, v in enumerate(counts)}})
    out["primacy"] = prim

    # 3b. Softmax position flag: simulate on fresh seeds
    sim = {}
    for spec in ("softmax:0.5", "uniform", "bayes"):
        pos = []
        for seed in range(50_000, 52_000):
            tp = make_tapes(seed, 60)
            for t, r in enumerate(run_episode(Cell(rho=0.0), tp, make_baseline(spec), 60)):
                order = [tp.labels[i] for i in tp.orders[t]]
                pos.append(order.index(r["label"]))
        counts = np.bincount(pos, minlength=8)
        sim[spec] = {"n_choices": int(counts.sum()), "chi2_p": float(chisquare(counts).pvalue),
                     "shares": [float(v / counts.sum()) for v in counts]}
    out["position_simulation_fresh_seeds"] = sim

    (OUT / "posthoc.json").write_text(json.dumps(out, indent=1))
    pd.DataFrame(tost).to_csv(OUT / "h3_tost.csv", index=False)
    pd.DataFrame(prim).to_csv(OUT / "primacy.csv", index=False)
    print(json.dumps({k: v for k, v in out.items() if k != "primacy"}, indent=1))
    print(pd.DataFrame(prim)[["coordinator", "pos1_share", "ci95_lo", "ci95_hi", "chi2_p"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
