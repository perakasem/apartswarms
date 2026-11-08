"""Checklist (review 2.12) and hypotheses H1-H4 for every coordinator x cell.

Outputs in results/<experiment>/analysis/:
  confirmatory.csv       confirmatory role only: H1/H2/H3 family, Holm, verdicts
  summary.csv            one row per coordinator x cell, every estimate with CIs
  h2.csv                 H2 per coordinator x slice: fitted linear root (primary) and
                         sign-change contrast / interpolated switch point (secondary)
  retry_lengths.csv      reply/notes length in rounds with vs without API retries
  did_k_sensitivity.csv  DiD for k in {1, 3, 5, 10}
  regression.csv         GEE (bias-reduced SEs) / mixed-logit interaction
  fallback_by_cell.csv   fallback rates, exclusions, differential-rate test
  script_fidelity.csv, position_bias.csv, table_main.tex, analysis.json
The pilot gets the full analysis (decisions §2.3); its seeds are disjoint.

  uv run scripts/analyze.py --config configs/confirmatory.yaml          # final, B=5000
  uv run scripts/analyze.py --config configs/confirmatory.yaml --B 500  # quick look
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.analysis import (_event_sums, assignment_events, did_from_sums, h2_linear,  # noqa: E402
                          h2_test, holm, manipulation_check, paired_did_gap, position_bias,
                          regression_did, replay_audit, retry_length_check, script_fidelity,
                          summarize_cell)
from sas.codehash import analysis_code_hash  # noqa: E402
from sas.grid import check_stages, load_experiment  # noqa: E402
from sas.params import Payoffs, rho_star  # noqa: E402
from sas.prereg import (B_FINAL, H3_COMPARATOR, H3_UPPER_BOUND, K, MAX_FALLBACK_RATE,  # noqa: E402
                        SESOI, in_core_slice, is_core)

SLICE = ["feedback", "c", "pi", "visibility", "framing", "tone"]


def fmt_ci(x, lo, hi, nd=3):
    return f"{x:.{nd}f} [{lo:.{nd}f}, {hi:.{nd}f}]" if np.isfinite(x) else "--"


def preamble_types(df: pd.DataFrame) -> pd.DataFrame:
    """Decision 1: DESCRIPTIVE, not causal (preamble rounds are not random).
    Per LLM x cell: share of assignments to each worker type in rounds whose
    used reply had a preamble vs rounds without one."""
    from sas.params import TYPES
    rows = []
    llm = df[(df["kind"] == "llm") & df["preamble"].notna()] if "preamble" in df else df.iloc[0:0]
    for (coord, cell), g in llm.groupby(["coordinator", "cell_id"]):
        for flag, h in g.groupby(g["preamble"].astype(bool)):
            shares = h["wtype"].value_counts(normalize=True)
            rows.append({"coordinator": coord, "cell_id": cell, "preamble": bool(flag), "rounds": len(h),
                         **{f"share_{t}": float(shares.get(t, 0.0)) for t in TYPES}})
    return pd.DataFrame(rows)


def fallback_table(df: pd.DataFrame, excluded: list) -> pd.DataFrame:
    """Fallback rate and exclusions per coordinator x cell, with a chi-square
    test of whether the fallback rate differs across cells (per coordinator).
    A differential rate would make the >10% exclusion rule a selection effect."""
    from scipy.stats import chi2_contingency
    rows = []
    for (coord, cell), g in df.groupby(["coordinator", "cell_id"]):
        runs = g["run_id"].unique()
        rows.append({"coordinator": coord, "cell_id": cell, "rounds": len(g),
                     "fallback_rounds": int(g["fallback"].sum()),
                     "fallback_rate": float(g["fallback"].mean()),
                     "runs": len(runs), "runs_excluded": int(sum(r in excluded for r in runs))})
    t = pd.DataFrame(rows)
    t["differential_p"] = np.nan
    for coord, g in t.groupby("coordinator"):
        table = np.array([g["fallback_rounds"], g["rounds"] - g["fallback_rounds"]])
        if len(g) > 1 and table[0].sum() > 0:
            t.loc[g.index, "differential_p"] = float(chi2_contingency(table)[1])
    return t


def confirmatory_family(summary: pd.DataFrame, h2: pd.DataFrame) -> pd.DataFrame:
    """H1, H2, H3 per LLM model (sas/prereg.py), Holm across the whole family."""
    rows = []
    llm = summary[summary["kind"] == "llm"]
    for coord in sorted(llm["coordinator"].unique()):
        core = llm[(llm["coordinator"] == coord) & llm.apply(is_core, axis=1)]
        if len(core):
            r = core.iloc[0]
            rows.append({"coordinator": coord, "hypothesis": "H1", "estimate": r["did"],
                         "lo": r["did_lo"], "hi": r["did_hi"], "p": r["did_p"],
                         "predicted_sign": -1, "tost_equivalent": r["did_tost_equivalent"],
                         "n_runs": r["n_runs"]})
            if "h3_gap" in r and pd.notna(r.get("h3_p")):
                rows.append({"coordinator": coord, "hypothesis": "H3", "estimate": r["h3_gap"],
                             "lo": r["h3_gap_lo"], "hi": r["h3_gap_hi"], "p": r["h3_p"],
                             "predicted_sign": 0, "n_runs": r["h3_n_seeds"]})
        # H2 (decisions §2.5): slope of the linear-in-rho DiD fit; its root is the
        # empirical switch point, reported next to rho* and the Bayes roots.
        hh = h2[(h2["coordinator"] == coord) & h2.apply(in_core_slice, axis=1)] if len(h2) else h2
        if len(hh) and pd.notna(hh.iloc[0].get("h2lin_slope_p")):
            r = hh.iloc[0]
            rows.append({"coordinator": coord, "hypothesis": "H2", "estimate": r["h2lin_slope"],
                         "lo": r["h2lin_slope_lo"], "hi": r["h2lin_slope_hi"], "p": r["h2lin_slope_p"],
                         "predicted_sign": 1, "n_runs": r["h2_n_seeds"],
                         "root": r.get("h2lin_root"), "root_lo": r.get("h2lin_root_lo"),
                         "root_hi": r.get("h2lin_root_hi"), "rho_star": r["rho_star"]})
    fam = pd.DataFrame(rows)
    if fam.empty:
        return fam
    fam["p_holm"] = holm(fam["p"].tolist())

    def verdict(r):
        if r["p_holm"] < 0.05:
            if r["predicted_sign"] and np.sign(r["estimate"]) != r["predicted_sign"]:
                return "rejected null, opposite to predicted sign"
            return "rejected null"
        # == (not `is`): the flag is a numpy bool; NaN on H2/H3 rows compares False.
        if r["hypothesis"] == "H1" and r.get("tost_equivalent") == True:  # noqa: E712
            return "equivalent to zero within ±SESOI"
        return "inconclusive (not significant; not shown equivalent)"
    fam["verdict"] = fam.apply(verdict, axis=1)
    return fam


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--B", type=int, default=B_FINAL,
                    help=f"bootstrap replicates (final results: {B_FINAL})")
    ap.add_argument("--k", type=int, default=K, help="primary DiD window (pre-registered: 5)")
    ap.add_argument("--sesoi", type=float, default=SESOI, help="TOST bound on DiD (share units)")
    ap.add_argument("--include-fallback-runs", action="store_true",
                    help="keep LLM runs above the fallback-rate exclusion threshold")
    ap.add_argument("--print-code-hash", action="store_true",
                    help="print the analysis-code hash (for PREREGISTRATION.md) and exit")
    args = ap.parse_args()
    if args.print_code_hash:
        print(analysis_code_hash())
        return

    exp = load_experiment(args.config)
    df = pd.read_csv(exp.out_dir() / "data" / "rounds.csv.gz",
                     dtype={"notes": str, "raw": str, "served_model": str}, low_memory=False)
    out_dir = exp.out_dir() / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Decisions §1.5: e.g. the confirmatory analysis refuses any non-confirmatory run.
    check_stages(df["stage"].unique() if "stage" in df else ["unknown"], exp.stage)

    fb_rate = df.groupby("run_id")["fallback"].mean()
    excluded = sorted(fb_rate[fb_rate > MAX_FALLBACK_RATE].index)
    fallback = fallback_table(df, excluded)
    if not args.include_fallback_runs and excluded:
        df = df[~df["run_id"].isin(excluded)]
        print(f"excluded {len(excluded)} run(s) with > {MAX_FALLBACK_RATE:.0%} fallbacks")

    served = (df[df["kind"] == "llm"].groupby("coordinator")["served_model"]
              .agg(lambda x: sorted({m for v in x.dropna() for m in str(v).split(";") if m})).to_dict())
    # Decisions §1.3: flag any run whose served model changed between calls.
    per_run = (df[df["kind"] == "llm"].groupby("run_id")["served_model"]
               .agg(lambda x: sorted({m for v in x.dropna() for m in str(v).split(";") if m})))
    drift = {r: m for r, m in per_run.items() if len(m) > 1}
    if drift:
        print(f"WARNING: model drift within {len(drift)} run(s): {drift}")

    rows, sens, regs = [], [], []
    groups = list(df.groupby(["coordinator", "cell_id"]))
    for i, ((coord, cell_id), g) in enumerate(groups, 1):
        print(f"[{i}/{len(groups)}] {coord} {cell_id} ({g['run_id'].nunique()} runs)", flush=True)
        first = g.iloc[0]
        row = {"coordinator": coord, "kind": first["kind"], "cell_id": cell_id,
               "rho": first["rho"], **{k: first[k] for k in SLICE},
               "rho_star": rho_star(Payoffs(first["v"], first["c"], first["L"])),
               "eval_aware_rate": float(g["eval_aware"].mean()),
               "game_frame_rate": float(g["game_frame"].mean()),
               # Decision 1: share of used replies with text before the decision object
               # (LLM rounds with a usable reply; NaN for baselines).
               "preamble_rate": (float(g["preamble"].dropna().astype(bool).mean())
                                 if "preamble" in g and g["preamble"].notna().any() else np.nan)}
        row.update(summarize_cell(g, k=args.k, B=args.B, sesoi=args.sesoi))
        if first["rho"] > 0:   # decisions §2.1: validity check where audits can fire
            row.update(manipulation_check(g, B=args.B))
        # H3 is undefined under qualitative framing: the Bayes baseline
        # maximises points the LLM never sees (DEVIATIONS B10).
        h3_defined = first["framing"] == "points"
        row["h3_defined"] = h3_defined
        if coord not in (H3_COMPARATOR, H3_UPPER_BOUND) and h3_defined:
            for comp in (H3_COMPARATOR, H3_UPPER_BOUND):
                b = df[(df["coordinator"] == comp) & (df["cell_id"] == cell_id)]
                if not len(b):
                    continue
                res = paired_did_gap(g, b, k=args.k, B=args.B)
                if comp == H3_COMPARATOR:
                    row.update(res)            # h3_* and item-7 vs_bayes_share_*
                else:                          # rho-known upper bound: h3known_*
                    row.update({"h3known_" + k[3:]: v for k, v in res.items() if k.startswith("h3_")})
        rows.append(row)
        runs = sorted(g["run_id"].unique())
        for k in (1, 3, 5, 10):
            sens.append({"coordinator": coord, "cell_id": cell_id, "k": k,
                         "did": did_from_sums(_event_sums(assignment_events(g, k), runs))})
        regs.append({"coordinator": coord, "cell_id": cell_id, **regression_did(g, args.k)})

    summary = pd.DataFrame(rows)

    # H2 per coordinator x slice with >= 2 audit levels: linear root (>= 3
    # levels, primary) and the sign-change contrast / switch point (secondary).
    h2_rows = []
    for keys, g in df.groupby(["coordinator"] + SLICE):
        by_rho = {float(r): d for r, d in g.groupby("rho")}
        if len(by_rho) < 2:
            continue
        first = g.iloc[0]
        h2_rows.append({**dict(zip(["coordinator"] + SLICE, keys)),
                        "rho_star": rho_star(Payoffs(first["v"], first["c"], first["L"])),
                        **h2_linear(by_rho, k=args.k, B=args.B),
                        **h2_test(by_rho, k=args.k, B=args.B)})
    h2 = pd.DataFrame(h2_rows)

    audit = replay_audit(df)
    print(f"replay audit: {audit['mismatches']} mismatches in {audit['rounds_checked']:,} rounds"
          + ("  <-- DO NOT TRUST RESULTS" if audit["mismatches"] else ""))
    fid = script_fidelity(df)
    fid.to_csv(out_dir / "script_fidelity.csv", index=False)
    pos = position_bias(df)
    pos.to_csv(out_dir / "position_bias.csv", index=False)
    fallback.to_csv(out_dir / "fallback_by_cell.csv", index=False)
    pre = preamble_types(df)
    pre.to_csv(out_dir / "preamble_types.csv", index=False)
    retry = retry_length_check(df)
    retry.to_csv(out_dir / "retry_lengths.csv", index=False)
    if len(retry) and retry["flag_shorter"].any():
        print("WARNING: replies/notes are shorter in rounds that needed an API retry: "
              + ", ".join(retry.loc[retry["flag_shorter"], "coordinator"]))
    worst = fid["z"].abs().max()
    print(f"script fidelity: max |z| = {worst:.2f} over {len(fid)} type x theta x pi cells"
          + ("  <-- CHECK" if worst > 4 else ""))

    meta = {"settings": vars(args) | {"excluded_runs": excluded, "stage": exp.stage},
            "replay_audit": audit, "served_models": served, "model_drift_runs": drift,
            "analysis_code_hash": analysis_code_hash()}
    family = confirmatory_family(summary, h2) if exp.role == "confirmatory" else pd.DataFrame()
    if len(family):
        family.to_csv(out_dir / "confirmatory.csv", index=False)
        print(family[["coordinator", "hypothesis", "estimate", "p", "p_holm", "verdict"]].to_string(index=False))
    summary.to_csv(out_dir / "summary.csv", index=False)
    pd.DataFrame(sens).to_csv(out_dir / "did_k_sensitivity.csv", index=False)
    h2.to_csv(out_dir / "h2.csv", index=False)
    pd.DataFrame(regs).to_csv(out_dir / "regression.csv", index=False)
    (out_dir / "analysis.json").write_text(json.dumps(meta | {
        "confirmatory": family.replace({np.nan: None}).to_dict("records"),
        "summary": summary.replace({np.nan: None}).to_dict("records"),
        "h2": h2.replace({np.nan: None}).to_dict("records"),
    }, indent=1, default=str))
    write_latex(summary, out_dir / "table_main.tex", args.k)
    print(f"wrote {out_dir}")


def write_latex(summary: pd.DataFrame, path: Path, k: int):
    cols = ["coordinator", "rho", "feedback", "c", "pi"]
    s = summary.sort_values(["feedback", "c", "pi", "rho", "coordinator"])
    lines = [r"\begin{tabular}{llllrrrrr}", r"\toprule",
             r"Coordinator & $\rho$ & Feedback & $c$ & $\pi$ & Learning gap & Placebo gap & "
             rf"DiD ($k={k}$) & $\hat\lambda$ \\", r"\midrule"]
    for _, r in s.iterrows():
        name = str(r["coordinator"]).replace("baseline-", "").replace("_", r"\_")
        lines.append(
            f"{name} & {r['rho']:g} & {r['feedback']} & {r['c']:g} & {r['pi']:g} & "
            f"{fmt_ci(r['learning_gap'], r['learning_gap_lo'], r['learning_gap_hi'], 2)} & "
            f"{fmt_ci(r['placebo_gap'], r['placebo_gap_lo'], r['placebo_gap_hi'], 2)} & "
            f"{fmt_ci(r['did'], r['did_lo'], r['did_hi'], 3)} & "
            f"{fmt_ci(r['lambda'], r['lambda_lo'], r['lambda_hi'], 2)} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    path.write_text("\n".join(lines) + "\n")
    _ = cols


if __name__ == "__main__":
    main()
