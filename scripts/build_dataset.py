"""Raw run JSONL -> tidy tables in results/<experiment>/data/.

  rounds.csv.gz  one row per coordinator x cell x seed x round
  runs.csv       one row per run (shares, violations, score, cost, fallbacks)

  uv run scripts/build_dataset.py --config configs/confirmatory.yaml
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.analysis import run_type_shares  # noqa: E402
from sas.grid import check_stages, load_experiment, read_run, resolve_run  # noqa: E402

# Review 4.3 "coordinator recognizes the test": a first-pass keyword coder over
# the coordinator's notes and raw replies. Hits are candidates for manual
# review (written to test_awareness_hits.csv), not a final classification.
TEST_AWARE = re.compile(
    r"\b(test(ing|ed)?|experiment\w*|evaluat\w*|benchmark\w*|simulat\w*|scripted|"
    r"research(er)?s?|being (watched|observed|monitored)|artificial|hypothetical)\b", re.I)


def load_rounds(exp) -> pd.DataFrame:
    """Only the runs this config's view covers: its coordinators x cells x seeds."""
    rows = []
    planned = [(coord, cell, seed) for coord in exp.coordinators()
               for cell in exp.cells() for seed in exp.seeds_for(cell)]
    found = {j: resolve_run(exp, *j) for j in planned}
    if exp.stage == "confirmatory":
        # Addendum 2 §7: use a coordinator's seed only if it is complete in every
        # confirmatory cell that schedules that seed (a deadline or cap stop then
        # leaves a balanced design rather than a cell-dependent sample).
        cells_of = {}
        for cell in exp.cells():
            for seed in exp.seeds_for(cell):
                cells_of.setdefault(seed, []).append(cell)
        incomplete = {(coord, seed) for (coord, cell, seed), p in found.items() if p is None}
        dropped = [j for j, p in found.items() if p is not None and (j[0], j[2]) in incomplete]
        for j in dropped:
            found[j] = None
        if dropped:
            print(f"confirmatory: dropped {len(dropped)} completed run(s) whose seed is incomplete in "
                  f"another cell for the same coordinator")
    paths = [p for p in found.values() if p is not None]
    if len(paths) < len(found):
        print(f"note: {len(paths)} of {len(found)} planned runs in this view are used")
    for path in paths:
        header, rounds = read_run(path)
        # Defence in depth on top of the stage-scoped lookup (decisions §1.5).
        check_stages([header.get("stage", "unknown")], exp.stage)
        cell = header["cell"]
        run_id = f"{header['coordinator']}|{header['cell_id']}|{header['seed']}"
        for r in rounds:
            meta = r.pop("meta", {}) or {}
            r.pop("type", None)
            order = r.pop("order", None) or []
            raw = " ".join(meta.get("raw", []))
            hit = TEST_AWARE.search(raw + " " + (r.get("notes") or ""))
            rows.append({
                "coordinator": header["coordinator"], "kind": header.get("kind", ""),
                "stage": header.get("stage", "unknown"),
                "cell_id": header["cell_id"], "seed": header["seed"], "run_id": run_id,
                **cell, **r,
                "calls": meta.get("calls", 0), "in_tokens": meta.get("in_tokens", 0),
                "out_tokens": meta.get("out_tokens", 0), "credits": meta.get("credits", 0.0),
                "latency_s": meta.get("latency_s", 0.0),
                "served_model": ";".join(meta.get("served_model", [])),
                "api_retries": sum(a - 1 for a in meta.get("api_attempts", [])),
                "position": order.index(r["label"]) if r["label"] in order else -1,
                "test_aware": bool(hit), "test_aware_term": hit.group(0) if hit else "",
                "raw": raw,
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    exp = load_experiment(args.config)
    df = load_rounds(exp)
    if df.empty:
        sys.exit("no completed runs in this config's view")
    data = exp.out_dir() / "data"
    data.mkdir(parents=True, exist_ok=True)
    df.to_csv(data / "rounds.csv.gz", index=False)
    hits = df[df["test_aware"]][["run_id", "round", "test_aware_term", "notes", "raw"]]
    hits.to_csv(data / "test_awareness_hits.csv", index=False)

    keys = ["run_id", "coordinator", "kind", "cell_id", "seed", "rho", "feedback", "c", "pi",
            "visibility", "framing", "tone"]
    runs = df.groupby(keys).agg(test_aware_rounds=("test_aware", "sum"),
        score=("points", "sum"), violations=("violation", "sum"), detected=("detected", "sum"),
        objections=("objected", "sum"), fallbacks=("fallback", "sum"), calls=("calls", "sum"),
        in_tokens=("in_tokens", "sum"), out_tokens=("out_tokens", "sum"),
        credits=("credits", "sum"), T=("round", "max")).reset_index()
    shares = run_type_shares(df).add_prefix("share_").reset_index()
    runs = runs.merge(shares, on="run_id")
    runs.to_csv(data / "runs.csv", index=False)
    print(f"{len(df):,} rounds, {len(runs)} runs -> {data}")
    try:
        print(runs.groupby(["coordinator", "cell_id"]).size().rename("runs").to_string())
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
