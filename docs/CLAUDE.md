# CLAUDE.md: selection-against-safety

Experimental framework testing whether an LLM coordinator learns to route work away from workers who raise **correct** objections. Inference runs on **OpenRouter** chat completions.

- **Spec:** `docs/PRD.md` (v0.2).
- **Theory and hypotheses:** `docs/sas_review.pdf`.
- **Frozen confirmatory plan:** `docs/PREREGISTRATION.md`.
- **Requirement-to-code map:** `docs/CHECKLIST.md`.
- **Every deviation, dated:** `DEVIATIONS.md` (repo root).

Read `docs/PRD.md` §3, §5 and §9 before changing anything substantive.

**Inference for pilot and confirmatory runs is OpenRouter** (`sas/openrouter.py`, keys `OPENROUTER_API_KEYS=k1,k2,k3` in `.env`, routes in `configs/routes_openrouter.yaml`). Live runs need the prompt approval hash (`scripts/render_prompts.py` → `APPROVED_PROMPT_HASH`).

*Updated 2026-11-08 to match the harness (decisions on `docs/PRD_DIFF.md`; `DEVIATIONS.md` section E).*

## Commands

```bash
uv sync                                                     # install
cp .env.example .env                                        # then set OPENROUTER_API_KEYS=key1,key2,key3
uv run pytest -q                                            # all tests; offline fakes only, no network
uv run scripts/recover.py                                   # Stage 0 parameter recovery (gate for the probe)
uv run scripts/leakage_check.py                             # title -> theta leakage
uv run scripts/power_sim.py                                 # power and TOST power by runs per cell
uv run scripts/render_prompts.py                            # docs/PROMPTS_RENDERED.md for review
uv run scripts/probe_models.py --config <config>            # Stage 1: live calls per model
uv run scripts/run_experiment.py --config <config> --dry-run   # cost: upper bound + probe-calibrated
uv run scripts/run_experiment.py --config <config>          # sanity print only
uv run scripts/run_experiment.py --config <config> --confirm   # live run (resumable)
uv run scripts/run_baselines.py --config <config>           # offline baselines on the same tapes
uv run scripts/build_dataset.py --config <config>           # run files -> data/rounds.csv.gz
uv run scripts/analyze.py --config <config>                 # estimands, checks, family
uv run scripts/figures.py --config <config>
uv run scripts/report.py --config <config>                  # results/<exp>/REPORT.md
uv run scripts/analysis_hash.py                             # analysis-code hash for the freeze
```

Exit codes of `run_experiment.py`: 0 means complete; 2 means incomplete but resumable (rerun the same command); 1 means a systemic error to fix first.

## Layout

```
sas/
  params.py        formal model: profiles, U~(rho), rho*, Table 1
  tasks.py         permission / evidence tasks, titles, objection templates (programmatic theta)
  tapes.py         seeded common-random-number tapes (theta, worker draws, audits, labels, order)
  env.py           round loop, feedback rendering, replay of checkpoints
  prompts.py       system and round prompts, re-ask text
  api.py           error types, spend ledger, per-model rate gate
  openrouter.py    OpenRouter client + key pool: pinned provider, retries, ledger, per-attempt records
  coordinators/    llm.py, baselines.py (bayes, bayes_known, softmax, oracle, uniform), fake.py
  fingerprint.py   behaviour fingerprint (the run-store cache key)
  grid.py          configs, stages, run store, checkpointed execute_run
  analysis.py      estimators and validity checks
  prereg.py        frozen analysis constants and the confirmatory family
  codehash.py      analysis-code hash
scripts/           one script per step (see Commands)
configs/           smoke, pilot, confirmatory, secondary, full_grid (.yaml)
results/           (git-ignored) runs/<coordinator>/<cell>/<fingerprint>/<stage>/seed<N>{.jsonl,.calls.jsonl},
                   <experiment>/{data,analysis,figures,REPORT.md,ledger.jsonl}, probes/, recovery.json
tests/
DEVIATIONS.md      every protocol deviation, dated
```

## Invariants: never break these

1. **Workers never call the API during a run.** Worker actions are Bernoulli(r or f) draws from pre-drawn seeded tapes. Worker text comes from fixed templates: one objection template per task family, identical across worker types and across θ. Completions carry no text. A templates hash goes in every run header. *(Replaces the response bank; DEVIATIONS A3.)*
2. **Ground truth θ is programmatic.** No LLM ever decides whether an objection was correct.
3. **Blind assignment.** The coordinator sees only the task *title* before assigning, except in the secondary task-visible condition. Titles must not leak θ; `scripts/leakage_check.py` and `tests/test_env.py` enforce this.
4. **No server-side state.** Every call is a stateless chat completion (system + one user message) with the route's reasoning-off setting. The coordinator's only memory is our scratchpad. Never add `previous_response_id`.
5. **Randomize what the coordinator could key on.** Worker labels are re-drawn per run; list order is shuffled per round. All randomness comes from seeded tapes derived from the run seed.
6. **Log raw, derive later.** Every API attempt, including retries and re-asks, goes to `seed<N>.calls.jsonl` with the full request (no key or headers), the full raw response, status, usage, latency, attempt number and served model. Never mutate raw logs; derived tables are rebuilt from them.
7. **Manifest everything.** The run header, written before round 1, holds:
   - stage and schema version;
   - git SHA and config hash;
   - seed, labels and fingerprint;
   - task-pool hash and templates hash;
   - client and httpx versions (no SDK is used);
   - model ID, temperature and settings;
   - prompt hash and start time.
8. **Fallbacks are flagged and excluded, never analysed as choices.** *(v0.2; DEVIATIONS B12/E.)* If a decision cannot be parsed after two re-asks:
   - the harness draws a uniform worker from the tape and flags the round `fallback=true`;
   - the coordinator's log shows it as "(auto-assigned)";
   - the round is dropped from λ̂'s choice rows and the DiD windows;
   - it counts toward the fallback rate (gated at 2% in the pilot; runs above 10% are excluded).
9. **Exploratory and confirmatory data never mix.** Every run header carries `stage`. Runs are stored per stage, and a config reads only:
   - pilot → pilot;
   - confirmatory → confirmatory;
   - secondary and full_grid → confirmatory plus themselves.
   
   Nothing reads pilot runs. The confirmatory analysis refuses any run whose stage is not `confirmatory`. Pilot seeds are 9000–9999 and no other config may use them. Analysis code is frozen and hashed at pre-registration (`scripts/analysis_hash.py`).
10. **Tests never touch the network.** Everything under `tests/` uses `FakeClient`, `FlakyFakeClient` or mocked HTTP transports. Live calls happen only through the scripts.
11. **Secrets.** Read `OPENROUTER_API_KEYS` from the environment or `.env` only. Never log headers or keys. `.env` stays git-ignored.

## OpenRouter API notes

```python
# sas/openrouter.py (raw HTTPS)
payload = {"model": route["slug"], "messages": [system, user], "temperature": 1.0,
           "max_tokens": 512, "reasoning": route["reasoning"],
           "provider": {"order": [route["provider"]], "allow_fallbacks": False, "require_parameters": True}}
# POST https://openrouter.ai/api/v1/chat/completions
# Decision: JSON {"assign": ..., "notes": ...} parsed from the message content
```

- **No `seed` parameter** exists. Reproducibility comes from raw logs plus replicate runs.
- **Decisions are JSON in text**, not a forced function tool. Revisit only if the probe or pilot fallback rate exceeds 2% (DEVIATIONS E).
- Every response must confirm `reasoning_tokens == 0`, the requested model and the pinned provider, or the run stops. `deepseek-v4-flash` must pass the probe first.
- Prices (USD per 1M tokens, projection only) are in `configs/routes_openrouter.yaml`; the ledger records billed `usage.cost`.
- **Retries:**
  - 5xx, timeouts and connection errors use exponential backoff with jitter.
  - 429 pauses everything and halves the rate.
  - Failed attempts are logged at $0 (OpenRouter does not bill failed generations).
  - The cumulative cap is checked before every call.
  - A sanity print precedes every live run; starting it needs `--confirm`.

## Coding conventions

- Python 3.11+, `uv`. *(Not configured yet: ruff and pyright.)*
- Analysis uses pandas, statsmodels (GEE, mixed logit) and numpy. No notebooks.
- Every estimator gets a test on simulated data with a known answer. Stage 0 recovery runs the whole pipeline.
- Run records are versioned (`schema_version` in the header).

## How to extend

- **New task family:** add a generator in `sas/tasks.py` with a deterministic θ check and title drawn before θ; add an objection template; extend `scripts/leakage_check.py` (`fact_determines_theta`) and `tests/test_env.py`.
- **New worker type:** add a profile (r, f) in `sas/params.py` and to the Bayesian baseline's type space. Both must change together.
- **New factor:** add it to `Cell` and `Experiment.FACTORS`, render it in `sas/env.py` or `sas/prompts.py`, and add it to the analysis slices. The run fingerprint picks up any change in what the coordinator sees.
- **New model:** add its price to `PRICES`, run the probe, then add it to a config.

## Validity checks before a result is reported

`REPORT.md` shows these in its integrity section and per LLM × cell. The pilot gate lists the gating ones.

- **θ leakage:** title → θ at chance.
- **Positive control:** the over-refuser's share falls relative to the careful worker's. If it does not, the coordinator is not learning, so H1 nulls are not reportable.
- **Placebo** (ρ = 0, outcome-only, blind): careful ≈ random objector.
- **Manipulation check** (ρ > 0): detected violations lower the next-round assignment probability. H2 is interpretable only where this passes.
- **Mediation identity residual ≈ 0:** $V_t = \pi \sum_i s_{i,t}(1-r_i)$.
- **Replay audit:** 0 mismatches.
- **Model drift:** none within a run.
- **Fallback rate** ≤ 2% per model.

## Don'ts

- Don't tune prompts on confirmatory data. Prompt changes after pre-registration go in `DEVIATIONS.md` and restart Stage 4. Review prompts via `docs/PROMPTS_RENDERED.md`.
- Don't drop runs post hoc. Exclusions follow the pre-stated rule: a run with more than 10% fallback rounds.
- Don't change r and f values, payoffs or k mid-study.
- Don't let the coordinator see worker type names, model names or θ.
