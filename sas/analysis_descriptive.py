"""Secondary, descriptive analyses added after the pilot and before the freeze
(DEVIATIONS G25). Not in the confirmatory family; no p-values enter Holm.

Run-level share gap: per run, S = share(careful) - share(complier) over the
late window (rounds 31-60 at T = 60; the second half of the run), coordinator decisions only (fallback rounds are
dropped). Reported per coordinator x cell with run-bootstrap CIs, the
contrast S(rho=1) - S(rho=0) per coordinator, and LLM - Bayes(rho-uncertain)
at rho = 0 on paired seeds.

Lock-in: per run, the late-window maximum worker share m = max_w share of
rounds 31-60 going to worker w (top worker w*), and its onset: the earliest
round t (w* assigned at t) from which w*'s share of rounds t-60 is at least
m, i.e. how early the late-window concentration was already in place. A run
locked onto one worker from round 8 has m = 1 and onset 8; a uniform chooser
has m ~ 0.27 and onset near 31. Distributions are compared with the Bayes
and softmax baselines (quantiles, and mean differences on paired seeds).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .prereg import H3_COMPARATOR

SOFTMAX = "baseline-softmax0.5"
COMPARATORS = (H3_COMPARATOR, SOFTMAX)


def _boot_mean(x: np.ndarray, rng, B: int) -> tuple[float, float, float]:
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    boot = x[rng.integers(0, len(x), (B, len(x)))].mean(axis=1)
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return float(x.mean()), float(lo), float(hi)


def run_level(df: pd.DataFrame) -> pd.DataFrame:
    """One row per run: S, late-window max share, top slot, onset round."""
    rows = []
    for run_id, g in df.sort_values("round").groupby("run_id", sort=False):
        first = g.iloc[0]
        T = int(g["round"].max())
        late_lo = T // 2 + 1                     # second half: rounds 31-60 at T = 60
        dec = g[~g["fallback"].astype(bool)]
        late = dec[dec["round"] >= late_lo]
        row = {"run_id": run_id, "coordinator": first["coordinator"], "kind": first["kind"],
               "cell_id": first["cell_id"], "rho": float(first["rho"]), "seed": int(first["seed"]),
               "late_decisions": len(late)}
        if len(late):
            w = late["wtype"]
            row["S"] = float((w == "careful").mean() - (w == "complier").mean())
            counts = late["slot"].value_counts()
            top = int(counts.index[0])
            m = float(counts.iloc[0] / len(late))
            onset = np.nan
            rounds, slots = dec["round"].to_numpy(), dec["slot"].to_numpy()
            for i in range(len(dec)):
                if slots[i] == top and (slots[i:] == top).mean() >= m - 1e-12:
                    onset = int(rounds[i])
                    break
            row.update(max_share=m, top_slot=top, top_wtype=late.loc[late["slot"] == top, "wtype"].iat[0],
                       onset=onset)
        rows.append(row)
    out = pd.DataFrame(rows)
    for col in ("S", "max_share", "top_slot", "top_wtype", "onset"):
        if col not in out:
            out[col] = np.nan
    return out


def share_gap_table(runs: pd.DataFrame, B: int = 5000, seed: int = 0) -> pd.DataFrame:
    """Mean S by coordinator x cell; S(rho_max) - S(rho_min); LLM - Bayes at rho = 0."""
    rng = np.random.default_rng(seed)
    out = []
    for (coord, cell), g in runs.groupby(["coordinator", "cell_id"]):
        m, lo, hi = _boot_mean(g["S"].to_numpy(float), rng, B)
        out.append({"coordinator": coord, "cell_id": cell, "rho": g["rho"].iat[0], "contrast": "mean S",
                    "n_runs": len(g), "estimate": m, "lo": lo, "hi": hi})
    for coord, g in runs.groupby("coordinator"):
        rhos = sorted(g["rho"].unique())
        if len(rhos) < 2 or 0.0 not in rhos:
            continue
        a = g[g["rho"] == 1.0]["S"].to_numpy(float) if 1.0 in rhos else None
        b = g[g["rho"] == 0.0]["S"].to_numpy(float)
        if a is None or not len(a) or not len(b):
            continue
        boot = (a[rng.integers(0, len(a), (B, len(a)))].mean(1) - b[rng.integers(0, len(b), (B, len(b)))].mean(1))
        lo, hi = np.quantile(boot, [0.025, 0.975])
        out.append({"coordinator": coord, "cell_id": "rho1 - rho0", "rho": np.nan, "contrast": "S(rho=1) - S(rho=0)",
                    "n_runs": f"{len(a)}/{len(b)}", "estimate": float(a.mean() - b.mean()),
                    "lo": float(lo), "hi": float(hi)})
    out += _paired(runs, "S", rho=0.0, comparators=(H3_COMPARATOR,), rng=rng, B=B, label="LLM - Bayes, S")
    return pd.DataFrame(out)


def _paired(runs, col, rho, comparators, rng, B, label) -> list[dict]:
    out = []
    at = runs[runs["rho"] == rho]
    for comp in comparators:
        base = at[at["coordinator"] == comp].set_index("seed")[col]
        if not len(base):
            continue
        for coord, g in at[at["kind"] == "llm"].groupby("coordinator"):
            s = g.set_index("seed")[col]
            common = sorted(set(s.index) & set(base.index))
            d = (s.loc[common] - base.loc[common]).to_numpy(float)
            m, lo, hi = _boot_mean(d, rng, B)
            out.append({"coordinator": coord, "cell_id": at[at["coordinator"] == coord]["cell_id"].iat[0],
                        "rho": rho, "contrast": f"{label} ({comp}, paired seeds)", "n_runs": len(common),
                        "estimate": m, "lo": lo, "hi": hi})
    return out


def lockin_table(runs: pd.DataFrame, B: int = 5000, seed: int = 0) -> pd.DataFrame:
    """Lock-in distributions per coordinator x cell, and LLM - baseline mean gaps on paired seeds."""
    rng = np.random.default_rng(seed)
    out = []
    for (coord, cell), g in runs.groupby(["coordinator", "cell_id"]):
        for col in ("max_share", "onset"):
            x = g[col].to_numpy(float)
            x = x[np.isfinite(x)]
            if not len(x):
                continue
            m, lo, hi = _boot_mean(x, rng, B)
            q10, q50, q90 = np.quantile(x, [0.1, 0.5, 0.9])
            out.append({"coordinator": coord, "cell_id": cell, "rho": g["rho"].iat[0], "measure": col,
                        "contrast": "distribution", "n_runs": len(x), "mean": m, "lo": lo, "hi": hi,
                        "q10": q10, "median": q50, "q90": q90,
                        "share_ge_0.8": float((g["max_share"] >= 0.8).mean()) if col == "max_share" else np.nan})
    for rho in sorted(runs["rho"].unique()):
        for col in ("max_share", "onset"):
            for r in _paired(runs, col, rho, COMPARATORS, rng, B, label=f"LLM - baseline, {col}"):
                est = r.pop("estimate")
                out.append({**r, "measure": col, "mean": est})
    return pd.DataFrame(out)
