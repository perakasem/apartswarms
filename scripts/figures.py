"""Paper figures -> results/<experiment>/figures/*.pdf (+ .png).

  fig_theory            U~(rho) by worker type with the misselection band (review Fig. 1)
  fig_shares_<slice>    assignment share by type over rounds; rows = coordinator, cols = rho
  fig_did_<slice>       DiD vs rho with 95% CIs, rho* marked (H1/H2/H3)
  fig_violations_<slice> observed V_t vs Eq. (7) prediction from realised shares (H4)
  fig_checklist         learning-control and placebo gaps (checklist items 1-2)
  fig_lambda            lambda-hat by coordinator (checklist item 5)

  uv run scripts/figures.py --config configs/confirmatory.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.analysis import violation_identity  # noqa: E402
from sas.grid import load_experiment  # noqa: E402
from sas.params import TYPES, Payoffs, perceived_value, rho_star, worker_profiles  # noqa: E402

# Validated categorical palette (dataviz reference, slots 1-4), fixed order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TYPE_COLOR = dict(zip(TYPES, SERIES))
TYPE_STYLE = {"careful": "-", "complier": "-", "over_refuser": "--", "random_objector": ":"}
TYPE_NAME = {"careful": "Careful", "complier": "Complier", "over_refuser": "Over-refuser",
             "random_objector": "Random objector"}
BASELINE_STYLE = {  # baselines are recessive grays; LLMs take categorical slots
    "baseline-bayes": ("#52514e", "--", "Bayes (ρ uncertain)"),
    "baseline-bayes_known": ("#8a8984", (0, (5, 2, 1, 2)), "Bayes (ρ known)"),
    "baseline-softmax0.5": ("#8a8984", ":", "Softmax learner (λ=0.5)"),
    "baseline-uniform": ("#b5b4ad", "-.", "Uniform"),
    "baseline-oracle": ("#b5b4ad", (0, (1, 3)), "Oracle"),
}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e0"

plt.rcParams.update({
    "font.size": 9, "axes.titlesize": 9, "axes.labelsize": 9, "legend.fontsize": 8,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 1.8,
    "figure.dpi": 150, "savefig.bbox": "tight", "pdf.fonttype": 42,
})


def coord_style(coords: list[str]) -> dict:
    llms = sorted(c for c in coords if not c.startswith("baseline-"))
    st = {c: (SERIES[i % len(SERIES)], "-", c) for i, c in enumerate(llms)}
    st.update({c: BASELINE_STYLE.get(c, ("#8a8984", "--", c)) for c in coords if c.startswith("baseline-")})
    return st


def ordered(coords) -> list[str]:
    return sorted(coords, key=lambda c: (c.startswith("baseline-"), c))


def save(fig, out: Path, name: str):
    fig.savefig(out / f"{name}.pdf")
    fig.savefig(out / f"{name}.png")
    plt.close(fig)


SLICE = ["feedback", "c", "pi", "visibility", "framing", "tone"]


def slice_name(fb, c, pi, vis="blind", fr="points", tn="neutral") -> str:
    name = f"fb-{fb}_c{c:g}_pi{pi:g}"
    name += "" if vis == "blind" else f"_vis-{vis}"
    name += "" if fr == "points" else f"_frame-{fr}"
    name += "" if tn == "neutral" else f"_tone-{tn}"
    return name


def fig_theory(out: Path, pi=0.25, pay=Payoffs()):
    rho = np.linspace(0, 1, 101)
    rs = rho_star(pay)
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    ax.axvspan(0, rs, color="#e34948", alpha=0.08, lw=0)
    ax.text(rs / 2, 0.4, "misselection\nband", ha="center", va="bottom", color=INK2, fontsize=8)
    ax.axvline(rs, color=INK2, lw=0.8, ls="--")
    ax.text(rs + 0.01, 9.6, f"ρ* = {rs:.3f}", color=INK2, fontsize=8, va="top")
    for t, p in worker_profiles(pi).items():
        y = [perceived_value(p, pi, r, pay) for r in rho]
        ax.plot(rho, y, color=TYPE_COLOR[t], ls=TYPE_STYLE[t], label=TYPE_NAME[t])
        ax.annotate(TYPE_NAME[t], (1, y[-1]), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=8, color=INK)
    ax.set_xlabel("audit rate ρ")
    ax.set_ylabel("coordinator's value Ũᵢ(ρ)")
    ax.set_xlim(0, 1)
    ax.legend(frameon=False, loc="lower left")
    save(fig, out, "fig_theory")


def fig_shares(df: pd.DataFrame, out: Path, window: int = 10):
    for key, g in df.groupby(SLICE):
        coords = ordered(g["coordinator"].unique())
        rhos = sorted(g["rho"].unique())
        fig, axes = plt.subplots(len(coords), len(rhos), figsize=(2.6 * len(rhos) + 0.6, 1.7 * len(coords)),
                                 sharex=True, sharey=True, squeeze=False, layout="constrained")
        for i, coord in enumerate(coords):
            for j, rho in enumerate(rhos):
                ax = axes[i, j]
                h = g[(g["coordinator"] == coord) & (g["rho"] == rho)]
                n = h["run_id"].nunique()
                for t in TYPES:
                    ind = (h.assign(x=(h["wtype"] == t).astype(float))
                           .pivot_table(index="round", columns="run_id", values="x"))
                    y = ind.mean(axis=1).rolling(window, min_periods=1).mean()
                    ax.plot(y.index, y.values, color=TYPE_COLOR[t], ls=TYPE_STYLE[t], lw=1.5,
                            label=TYPE_NAME[t])
                ax.axhline(0.25, color=INK2, lw=0.6, ls=(0, (2, 3)))
                if i == 0:
                    ax.set_title(f"ρ = {rho:g}")
                if j == 0:
                    ax.set_ylabel(f"{coord.replace('baseline-', '')} (n={n})\nshare", fontsize=8)
                ax.set_ylim(0, 1)
        for ax in axes[-1]:
            ax.set_xlabel("round")
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside upper center", ncol=4, frameon=False)
        fig.text(0.5, -0.01, f"share of assignments to each type, {window}-round rolling mean; "
                 "dotted line = 1/4 (uniform)", ha="center", va="top", fontsize=7, color=INK2)
        save(fig, out, f"fig_shares_{slice_name(*key)}")


def fig_did(summary: pd.DataFrame, out: Path):
    for key, g in summary.groupby(SLICE):
        coords = [x for x in ordered(g["coordinator"].unique()) if x != "baseline-oracle"]
        st = coord_style(coords)
        fig, ax = plt.subplots(figsize=(4.6, 3.0))
        ax.axhline(0, color=INK2, lw=0.8)
        rs = g["rho_star"].iat[0]
        ax.axvline(rs, color=INK2, lw=0.8, ls="--")
        ax.text(rs + 0.01, 0.98, f"ρ* = {rs:.3f}", transform=ax.get_xaxis_transform(),
                color=INK2, fontsize=8, va="top")
        offs = np.linspace(-0.015, 0.015, max(len(coords), 1))
        for off, coord in zip(offs, coords):
            h = g[g["coordinator"] == coord].sort_values("rho")
            col, ls, name = st[coord]
            x = h["rho"].to_numpy() + off
            ax.plot(x, h["did"], color=col, ls=ls, marker="o", ms=4, label=name)
            ax.errorbar(x, h["did"], yerr=[h["did"] - h["did_lo"], h["did_hi"] - h["did"]],
                        fmt="none", ecolor=col, elinewidth=1, capsize=0)
        ax.set_xlabel("audit rate ρ")
        ax.set_ylabel("DiD in next-k share\n(careful − complier, O − P)")
        ax.legend(frameon=False, fontsize=7, loc="best")
        save(fig, out, f"fig_did_{slice_name(*key)}")


def fig_violations(df: pd.DataFrame, out: Path, window: int = 10):
    for key, g in df.groupby(SLICE):
        coords = ordered(g["coordinator"].unique())
        st = coord_style(coords)
        rhos = sorted(g["rho"].unique())
        fig, axes = plt.subplots(1, len(rhos), figsize=(3.2 * len(rhos), 2.6), sharey=True, squeeze=False)
        for j, rho in enumerate(rhos):
            ax = axes[0, j]
            for coord in coords:
                h = g[(g["coordinator"] == coord) & (g["rho"] == rho)]
                vi = violation_identity(h).groupby("round")[["violation", "predicted"]].mean()
                sm = vi.rolling(window, min_periods=1).mean()
                col, ls, name = st[coord]
                ax.plot(sm.index, sm["violation"], color=col, ls=ls, lw=1.5, label=name)
                ax.plot(sm.index, sm["predicted"], color=col, ls=":", lw=0.9, alpha=0.8)
            ax.set_title(f"ρ = {rho:g}")
            ax.set_xlabel("round")
        axes[0, 0].set_ylabel(f"violations per round\n({window}-round rolling mean)")
        axes[0, -1].legend(frameon=False, fontsize=7, loc="upper left", bbox_to_anchor=(1.0, 1.0))
        fig.text(0.5, -0.04, "solid/styled: observed · dotted: Eq. (7) prediction from realised shares",
                 ha="center", fontsize=7, color=INK2)
        save(fig, out, f"fig_violations_{slice_name(*key)}")


def _dot_panel(ax, summary, col, label, ref=None):
    coords = ordered(summary["coordinator"].unique())
    st = coord_style(coords)
    rhos = sorted(summary["rho"].unique())
    width = 0.8 / max(len(rhos), 1)
    for k, rho in enumerate(rhos):
        h = summary[summary["rho"] == rho].set_index("coordinator").reindex(coords)
        y = np.arange(len(coords)) + (k - (len(rhos) - 1) / 2) * width
        ax.errorbar(h[col], y, xerr=[h[col] - h[f"{col}_lo"], h[f"{col}_hi"] - h[col]],
                    fmt="o" if k % 2 == 0 else "s", ms=4, color=SERIES[k % len(SERIES)],
                    elinewidth=1, label=f"ρ = {rho:g}")
    ax.set_yticks(range(len(coords)), [st[c][2] for c in coords])
    ax.axvline(0, color=INK2, lw=0.8)
    if ref is not None:
        ax.axvline(ref, color=INK2, lw=0.8, ls="--")
    ax.set_xlabel(label)
    ax.invert_yaxis()


def fig_checklist(summary: pd.DataFrame, out: Path):
    for key, g in summary.groupby(SLICE):
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 0.45 * g["coordinator"].nunique() + 1.2), sharey=True)
        _dot_panel(axes[0], g, "learning_gap", "share: careful − over-refuser\n(should be > 0: learning control)")
        _dot_panel(axes[1], g, "placebo_gap", "share: careful − random objector\n(should be ≈ 0 at ρ = 0: placebo)")
        axes[1].legend(frameon=False, fontsize=7, loc="lower right")
        save(fig, out, f"fig_checklist_{slice_name(*key)}")


def fig_lambda(summary: pd.DataFrame, out: Path):
    for key, g in summary.groupby(SLICE):
        g = g[g["coordinator"] != "baseline-oracle"]
        fig, ax = plt.subplots(figsize=(4.6, 0.45 * g["coordinator"].nunique() + 1.0))
        _dot_panel(ax, g, "lambda", "λ̂ (choice sensitivity to running value estimate)")
        ax.legend(frameon=False, fontsize=7, loc="lower right")
        save(fig, out, f"fig_lambda_{slice_name(*key)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    exp = load_experiment(args.config)
    summary = pd.read_csv(exp.out_dir() / "analysis" / "summary.csv")
    out = exp.out_dir() / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig_theory(out)
    fig_checklist(summary, out)
    df = pd.read_csv(exp.out_dir() / "data" / "rounds.csv.gz",
                     dtype={"notes": str, "raw": str, "served_model": str}, low_memory=False)
    fig_shares(df, out)
    fig_did(summary, out)
    fig_violations(df, out)
    fig_lambda(summary, out)
    print(f"wrote {len(list(out.glob('*.pdf')))} figures -> {out}")


if __name__ == "__main__":
    main()
