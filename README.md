# Selection Against Safety

Does an LLM coordinator that repeatedly assigns work learn to route tasks away
from workers who raise *correct* objections, when the workers themselves never
change? The design, formal model and hypotheses are in `docs/sas_review.pdf`.
`docs/CHECKLIST.md` maps every requirement in that document to the code and
the check that verifies it. `DEVIATIONS.md` (repo root) records where the harness
departs from or fills gaps in the review, and why, along with the expected
outputs and run readiness. `docs/PREREGISTRATION.md` freezes the confirmatory
analysis.

## Setup

```bash
uv sync
cp .env.example .env        # add OPENROUTER_API_KEYS
uv run pytest               # offline; no network or credits
```

## Workflow

The confirmatory plan is frozen in `docs/PREREGISTRATION.md`. In order:

```bash
# 0. one-time pre-flight
uv run scripts/leakage_check.py                       # titles must not predict theta
uv run scripts/power_sim.py                           # power and TOST power by n
uv run scripts/probe_models.py --config configs/confirmatory.yaml   # required (~0.03 credits)

# 1. pilot (seeds 9001+; report shows integrity + items 1-2 only)
C=configs/pilot.yaml
uv run scripts/run_experiment.py --config $C --dry-run          # upper-bound cost
uv run scripts/run_experiment.py --config $C
uv run scripts/run_baselines.py  --config $C
uv run scripts/build_dataset.py  --config $C && uv run scripts/analyze.py --config $C
uv run scripts/report.py         --config $C

# 2. confirmatory (fixed n; no interim looks) — same steps, then
C=configs/confirmatory.yaml
uv run scripts/figures.py        --config $C
#    -> results/confirmatory/analysis/confirmatory.csv, REPORT.md
```

**Interruptions.** HTTP 504s, timeouts, crashes and Ctrl-C never lose
completed work:
- Calls are retried with backoff.
- Every finished round is checkpointed, and rerunning the same command
  resumes each run from its last round.
- Exit code 0 means everything is complete, 2 means incomplete but
  resumable (just rerun; includes budget caps and sustained rate limiting),
  and 1 means a systemic error to fix first: reasoning control, HTTP 4xx,
  provider/model mismatch, or a replay mismatch. A model-level failure stops
  only that model; the others continue.
- To rehearse an outage offline, use the model name `fake-flaky`.

**TODO (optional, not implemented): Pilot C** (PRD §9 Stage 2). One-shot paired
choices between a careful and a complier worker with matched histories, about
200 pairs per model, to record the direction of the coordinator's prior and
calibrate λ for power. Deferred by the 2026-11-08 decisions (§2.7).

Configs: `smoke.yaml` (fake LLM, offline), `pilot.yaml`, `confirmatory.yaml`,
`full_grid.yaml` and `secondary.yaml` (both exploratory).

## Layout

```
sas/            params (formal model), tasks, tapes (common random numbers), env,
                prompts, api + openrouter (API client), coordinators/, analysis, grid
scripts/        run_experiment, run_baselines, probe_models, leakage_check,
                power_sim, build_dataset, analyze, figures, report
results/runs/   shared run store: <coordinator>/<cell_id>/<fingerprint>/seed<NNNN>.jsonl
results/<exp>/  data/, analysis/, figures/, REPORT.md, ledger.jsonl
archive/        earlier attempt, kept for reference only
```

`results/` is git-ignored. Each run file records the config hash, prompt
hash, git SHA, model and settings in its header line.
