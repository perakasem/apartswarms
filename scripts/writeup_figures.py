"""Write-up figures for the confirmatory study (docs/CONFIRMATORY_RESULTS.md).

Reads only the frozen analysis outputs (results/confirmatory/analysis/*.csv),
the post-hoc exploratory outputs (results/confirmatory/exploratory/*.csv;
figures that use them say so) and run-file headers (timeline). Writes PNG
(200 dpi) and PDF to docs/figures/, and docs/figures/run_stats.json.

Colour: one fixed hue per model (qwen blue, deepseek orange, glm aqua; the
validated reference palette, light mode), baselines in neutral grays, and a
distinct marker per model so identity never rests on colour alone. Every
multi-series figure has a legend and direct labels.

  uv run scripts/writeup_figures.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "results/confirmatory/analysis"
X = ROOT / "results/confirmatory/exploratory"
OUT = ROOT / "docs/figures"
PRIMARY = "rho0_fb-outcome_c5_pi0.25"
RHO_STAR = 0.375
RHOS = [0.0, 0.25, 0.5, 1.0]

MODELS = ["qwen3.5-397b", "deepseek-v4-flash", "glm-5.2"]
NAME = {"qwen3.5-397b": "qwen3.5-397b", "deepseek-v4-flash": "deepseek-v4-flash", "glm-5.2": "glm-5.2",
        "baseline-bayes": "Bayes (ρ-uncertain)", "baseline-bayes_known": "Bayes (ρ-known)",
        "baseline-softmax0.5": "softmax (λ=0.5)", "baseline-uniform": "uniform", "baseline-oracle": "oracle"}
COLOR = {"qwen3.5-397b": "#2a78d6", "deepseek-v4-flash": "#eb6834", "glm-5.2": "#1baf7a",
         "baseline-bayes": "#52514e", "baseline-bayes_known": "#8a8984", "baseline-softmax0.5": "#a8a7a1",
         "baseline-uniform": "#c3c2b7"}
MARKER = {"qwen3.5-397b": "o", "deepseek-v4-flash": "s", "glm-5.2": "D",
          "baseline-bayes": "^", "baseline-bayes_known": "v", "baseline-softmax0.5": "P", "baseline-uniform": "X"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9, "axes.edgecolor": INK2,
    "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "legend.frameon": False, "lines.linewidth": 1.5,
    "lines.markersize": 6, "errorbar.capsize": 0,
})


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def zero(ax, axis="y"):
    (ax.axhline if axis == "y" else ax.axvline)(0, color=INK2, lw=0.8, zorder=1)


def fig1_h1(s):
    rows = MODELS + ["baseline-bayes", "baseline-bayes_known", "baseline-softmax0.5", "baseline-uniform"]
    d = s[s.cell_id == PRIMARY].set_index("coordinator").loc[rows]
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    y = np.arange(len(rows))[::-1]
    for yi, (c, r) in zip(y, d.iterrows()):
        ax.plot([r.did_lo, r.did_hi], [yi, yi], color=COLOR[c], lw=2, solid_capstyle="round")
        ax.plot(r.did, yi, MARKER[c], color=COLOR[c], ms=7, mec=SURF, mew=1)
        ax.text(1.02, yi, f"{r.did:+.3f} [{r.did_lo:+.3f}, {r.did_hi:+.3f}]", va="center",
                fontsize=8, color=INK2, transform=ax.get_yaxis_transform(), clip_on=False)
    zero(ax, "x")
    ax.axhline(y[len(MODELS) - 1] - 0.5, color=GRID, lw=1)
    ax.set_yticks(y, [NAME[c] for c in rows])
    ax.set_xlabel("DiD (next-5 share, careful − complier, after O − after P tasks)\n"
                  "← negative: routes away from careful workers after a correct objection")
    ax.set_title("H1 · Selection against correct objectors at ρ = 0 (n = 180 runs each)", loc="left")
    ax.set_xlim(-0.14, 0.04)
    ax.grid(axis="y", visible=False)
    save(fig, "fig1_h1_did_primary")


def fig2_h2(s, h2):
    fig, axes = plt.subplots(1, 3, figsize=(9.0, 3.0), sharey=True)
    bayes = s[s.coordinator == "baseline-bayes"].set_index("rho").sort_index()
    for ax, m in zip(axes, MODELS):
        d = s[s.coordinator == m].set_index("rho").sort_index()
        ax.plot(bayes.index, bayes.did, "--", color=COLOR["baseline-bayes"], lw=1.2, zorder=2)
        ax.plot(bayes.index, bayes.did, MARKER["baseline-bayes"], color=COLOR["baseline-bayes"], ms=5, zorder=2,
                label="Bayes (ρ-uncertain)")
        ax.errorbar(d.index, d.did, yerr=[d.did - d.did_lo, d.did_hi - d.did], fmt="none",
                    ecolor=COLOR[m], elinewidth=2, zorder=3)
        ax.plot(d.index, d.did, MARKER[m], color=COLOR[m], ms=7, mec=SURF, mew=1, zorder=4, label=NAME[m])
        r = h2[h2.coordinator == m].iloc[0]
        xs = np.linspace(0, 1, 50)
        ax.plot(xs, r.h2lin_intercept + r.h2lin_slope * xs, color=COLOR[m], lw=1.2, alpha=0.7, zorder=3,
                label="WLS fit")
        ax.axvline(RHO_STAR, color=INK2, lw=0.8, ls=":")
        ax.text(RHO_STAR + 0.015, 0.09, "ρ* = 0.375", fontsize=7.5, color=INK2, rotation=90, va="bottom")
        if np.isfinite(r.h2lin_root):
            ax.plot(r.h2lin_root, 0, "o", mfc=SURF, mec=COLOR[m], ms=6, mew=1.5, zorder=5)
            ax.text(0.98, 0.04, f"fitted root ρ̂ = {r.h2lin_root:.2f} [{r.h2lin_root_lo:.2f}, {r.h2lin_root_hi:.2f}]",
                    transform=ax.transAxes, fontsize=7.5, color=INK2, ha="right")
        zero(ax)
        ax.set_title(f"{NAME[m]}\nslope {r.h2lin_slope:+.2f} [{r.h2lin_slope_lo:+.2f}, {r.h2lin_slope_hi:+.2f}]",
                     loc="left", fontsize=9)
        ax.legend(loc="upper left", fontsize=7)
        ax.set_xlabel("audit probability ρ")
        ax.set_xticks(RHOS)
    axes[0].set_ylabel("DiD")
    fig.suptitle("H2 · DiD rises with audit probability and changes sign (n = 180 / 60 / 60 / 30 runs per ρ)",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    save(fig, "fig2_h2_did_by_rho")


def fig3_h3(fam, tost):
    fig, ax = plt.subplots(figsize=(6.2, 2.4))
    ax.axvspan(-0.05, 0.05, color="#f0efec", zorder=0)
    ax.text(0.0, 2.62, "±0.05 (post-hoc margin; H1's preregistered SESOI)", ha="center", fontsize=7.5, color=INK2)
    for yi, m in zip([2, 1, 0], MODELS):
        f = fam[(fam.coordinator == m) & (fam.hypothesis == "H3")].iloc[0]
        t = tost[tost.coordinator == m].iloc[0]
        ax.plot([t.ci95_lo, t.ci95_hi], [yi, yi], color=COLOR[m], lw=1.2)
        ax.plot([t.ci90_lo, t.ci90_hi], [yi, yi], color=COLOR[m], lw=3.5, solid_capstyle="round")
        ax.plot(f.estimate, yi, MARKER[m], color=COLOR[m], ms=7, mec=SURF, mew=1)
        ax.text(0.068, yi, f"{f.estimate:+.3f}  Holm p = {f.p_holm:.2f}  "
                f"{'within ±0.05' if t.equivalent_within_sesoi else 'not within ±0.05'}",
                va="center", fontsize=8, color=INK2)
    zero(ax, "x")
    ax.set_yticks([2, 1, 0], [NAME[m] for m in MODELS])
    ax.set_xlim(-0.09, 0.2)
    ax.set_ylim(-0.6, 2.9)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("DiD(LLM) − DiD(Bayes, ρ-uncertain), primary cell, paired seeds (n = 180)")
    ax.set_title("H3 · LLM vs rational learner: not rejected (thick = 90% CI, thin = 95% CI)", loc="left")
    save(fig, "fig3_h3_gap_vs_bayes")


def fig4_share_gap(sg):
    d = sg[sg.contrast == "mean S"]
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    series = MODELS + ["baseline-bayes", "baseline-softmax0.5"]
    off = dict(zip(series, np.linspace(-0.024, 0.024, len(series))))
    for c in series:
        g = d[d.coordinator == c].sort_values("rho")
        x = g.rho + off[c]
        ax.plot(x, g.estimate, "-" if c in MODELS else "--", color=COLOR[c], lw=1.5 if c in MODELS else 1.1)
        ax.errorbar(x, g.estimate, yerr=[g.estimate - g.lo, g.hi - g.estimate], fmt="none", ecolor=COLOR[c],
                    elinewidth=1.6)
        ax.plot(x, g.estimate, MARKER[c], color=COLOR[c], ms=6, mec=SURF, mew=1, label=NAME[c])
    zero(ax)
    ax.axvline(RHO_STAR, color=INK2, lw=0.8, ls=":")
    ax.set_xticks(RHOS)
    ax.set_xlim(-0.06, 1.08)
    ax.set_xlabel("audit probability ρ")
    ax.set_ylabel("S = share(careful) − share(complier), rounds 31–60")
    ax.set_title("Run-level share gap by audit probability (secondary, descriptive)", loc="left")
    ax.legend(loc="upper left", fontsize=7.5)
    save(fig, "fig4_share_gap_by_rho")


def fig5_lockin(rl):
    d = rl[rl.cell_id == PRIMARY]
    cols = MODELS + ["baseline-bayes", "baseline-softmax0.5"]
    fig, axes = plt.subplots(2, len(cols), figsize=(10, 4.2), sharey="row")
    for j, c in enumerate(cols):
        g = d[d.coordinator == c]
        for i, (col, bins, lab) in enumerate([("max_share", np.linspace(0, 1, 21), "top-worker share"),
                                              ("onset", np.arange(0, 64, 4), "onset round")]):
            x = g[col].dropna()
            w = np.ones(len(x)) / len(x)
            axes[i, j].hist(x, bins=bins, weights=w, color=COLOR[c], edgecolor=SURF, linewidth=1)
            axes[i, j].axvline(x.median(), color=INK, lw=1, ls="--")
            if col == "onset":
                axes[i, j].text(0.97, 0.93, f"median {x.median():.0f}", transform=axes[i, j].transAxes,
                                ha="right", va="top", fontsize=7.5, color=INK2)
            axes[i, j].set_xlabel(lab, fontsize=8)
            axes[i, j].grid(axis="x", visible=False)
        ge = (g.max_share >= 0.8).mean()
        axes[0, j].set_title(f"{NAME[c]}\nmedian {g.max_share.median():.2f}; ≥ 0.8: {ge:.0%}",
                             fontsize=8.5, loc="left")
    axes[0, 0].set_ylabel("share of runs")
    axes[1, 0].set_ylabel("share of runs")
    fig.suptitle("Lock-in at ρ = 0 (n = 180 runs each; secondary, descriptive). Top: the most-used worker's share of "
                 "rounds 31–60. Bottom: onset round (G25 definition)", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    save(fig, "fig5_lockin_primary")


def fig6_validity(s):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.1), sharey=True)
    off = dict(zip(MODELS, [-0.02, 0, 0.02]))
    for ax, (col, title) in zip(axes, [("learning_gap", "Positive control: careful − over-refuser share (> 0 required)"),
                                       ("placebo_gap", "Placebo: careful − random-objector share (≈ 0 required at ρ = 0 only)")]):
        for m in MODELS:
            g = s[s.coordinator == m].sort_values("rho")
            x = g.rho + off[m]
            ax.errorbar(x, g[col], yerr=[g[col] - g[col + "_lo"], g[col + "_hi"] - g[col]], fmt="none",
                        ecolor=COLOR[m], elinewidth=1.8)
            ax.plot(x, g[col], MARKER[m], color=COLOR[m], ms=6, mec=SURF, mew=1, label=NAME[m])
        zero(ax)
        ax.set_xticks(RHOS)
        ax.set_xlabel("audit probability ρ")
        ax.set_title(title, loc="left", fontsize=8.5)
    axes[1].axvspan(-0.06, 0.06, color="#f0efec", zorder=0)
    axes[0].set_ylabel("share difference")
    axes[0].legend(loc="upper left", fontsize=7.5)
    fig.suptitle("Validity checks re-estimated in the confirmatory data", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    save(fig, "fig6_validity_checks")


def fig7_primacy(prim):
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    for c in MODELS + ["baseline-uniform"]:
        r = prim[prim.coordinator == c].iloc[0]
        ys = [r[f"pos{i}"] for i in range(1, 9)]
        ax.plot(range(1, 9), ys, "-", color=COLOR[c], lw=1.5 if c in MODELS else 1.1)
        ax.plot(range(1, 9), ys, MARKER[c], color=COLOR[c], ms=6, mec=SURF, mew=1, label=NAME[c])
    ax.axhline(1 / 8, color=INK2, lw=0.8, ls=":")
    ax.text(1.0, 1 / 8 - 0.0015, "uniform 1/8", va="top", fontsize=7.5, color=INK2)
    ax.set_xticks(range(1, 9))
    ax.set_xlabel("position in the round's (shuffled) worker list")
    ax.set_ylabel("share of choices")
    ax.set_title("Primacy: LLMs over-pick the first-listed worker (all cells pooled)", loc="left")
    ax.legend(fontsize=7.5)
    save(fig, "fig7_position_primacy")


def figA_timeline():
    """Appendix: cumulative completed runs over wall-clock time, from run-file end events."""
    stats = {}
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    t0 = None
    ends = {}
    for m in MODELS:
        ts, resumed = [], 0
        for f in glob.glob(str(ROOT / f"results/runs/{m}/*/*/confirmatory/seed[0-9]*.jsonl")):
            if f.endswith(".calls.jsonl"):
                continue
            lines = Path(f).read_text().splitlines()
            end = json.loads(lines[-1])
            ts.append(end["time"])
            resumed += any('"event": "resume"' in x for x in lines)
        ends[m] = sorted(ts)
        stats[m] = {"runs": len(ts), "runs_resumed_from_checkpoint": resumed}
        t0 = min(ts) if t0 is None else min(t0, min(ts))
    import datetime as dt
    for m in MODELS:
        x = [dt.datetime.fromtimestamp(t) for t in ends[m]]
        ax.step(x, np.arange(1, len(x) + 1), where="post", color=COLOR[m], lw=1.5, label=NAME[m])
        ax.text(x[-1], len(x) + 6, NAME[m], fontsize=7.5, color=INK2,
                ha="left" if m == "deepseek-v4-flash" else "right")
        stats[m]["first_end"] = x[0].strftime("%H:%M:%S")
        stats[m]["last_end"] = x[-1].strftime("%H:%M:%S")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    ax.set_ylabel("completed runs (target 330)")
    ax.set_xlabel("wall-clock time, 2026-11-08 (EST)")
    ax.set_title("Data collection: flat stretches are provider rate-limit stops", loc="left")
    ax.legend(fontsize=7.5, loc="upper left")
    save(fig, "figA_collection_timeline")
    return stats


def main():
    s = pd.read_csv(A / "summary.csv")
    h2 = pd.read_csv(A / "h2.csv")
    fam = pd.read_csv(A / "confirmatory.csv")
    sg = pd.read_csv(A / "share_gap.csv")
    rl = pd.read_csv(A / "run_level.csv")
    tost = pd.read_csv(X / "h3_tost.csv")
    prim = pd.read_csv(X / "primacy.csv")
    fig1_h1(s)
    fig2_h2(s, h2)
    fig3_h3(fam, tost)
    fig4_share_gap(sg)
    fig5_lockin(rl)
    fig6_validity(s)
    fig7_primacy(prim)
    stats = figA_timeline()
    (OUT / "run_stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
