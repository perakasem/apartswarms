# Harness vs PRD and CLAUDE.md: all differences

> **Resolved 2026-11-08.** Every item below was decided (harness changed, or
> docs updated to v0.2). See `DEVIATIONS.md` section E. This file is kept as
> the historical diff against PRD v0.1.

**Date:** 2026-11-08.
**Compared:** the current harness (`sas/`, `scripts/`, `configs/`, `docs/`)
against `docs/PRD.md` (v0.1) and `docs/CLAUDE.md` (pre-update).

**Context.** The harness was built from `docs/sas_review.pdf` alone, plus the
external review pasted in chat. Neither PRD nor CLAUDE.md was available. This
file flags every difference for the team to evaluate. Nothing here has been
changed in code.

**Source of each choice in the harness:**
- **Review:** follows `sas_review.pdf` or the external review.
- **Mine:** my own judgment call where the sources were silent.
- **Gap:** something the PRD requires that I did not build.

**Effort to align with the PRD:**
- **S:** under an hour.
- **M:** a few hours.
- **L:** a day or more, or a restructure.

---

## 1. Violations of CLAUDE.md invariants

These matter most: CLAUDE.md calls them "never break".

| ID | Invariant | PRD / CLAUDE.md | Harness | Source | Effort |
|---|---|---|---|---|---|
| V1 | #8 No imputation | An unparseable decision after two re-asks → log `protocol_failure` and **skip the round**; never pick a worker on the model's behalf | After two re-asks, a uniform worker is **picked for the model** (`fallback=true`, drawn from the tape). The round is played, marked "(auto-assigned)" in the log, and excluded from λ̂ rows and Y windows | Mine (review B12) | S–M: a skip changes T per run and the replay logic |
| V2 | #4 No server-side state | Every call sends `store=False`, `agentic_memory=False`, `background=False`, with a hosted model ID (never `stack:`) | None of the three flags is sent (`sas/adaption.py:187`). The PRD says `store` defaults to false; `agentic_memory`'s default is unstated. There is no check against `stack:` IDs | Gap | S |
| V3 | #6 Log raw | Every API attempt goes to `events.jsonl` with the **full request, full raw response**, usage, latency and attempt number | Only the reply *text*, summed tokens and latency per round are stored. The request body and raw response JSON are not kept. Failed attempts appear only as ledger lines (status, estimated cost) | Gap | M |
| V4 | #7 Manifest everything | A separate `manifest.json` before round 1: git SHA, config hash, seeds, **bank hash, task-pool hash, SDK version**, model ID, temperature, sealed label-to-type map, start/end time, total credits | A header line in the run file has git SHA, config hash, seed, model, settings, labels and the behaviour fingerprint. There is no bank hash (no bank, see M1), no task-pool hash, no SDK version (no SDK, see S1), no end time or total credits. The label-to-type map is not sealed: `wtype` is in every round record | Gap | S–M |
| V5 | #9 Exploratory and confirmatory never mix | Stage 2–3 runs carry `stage: exploratory` in the manifest; **confirmatory analysis refuses them** | Separation is by seed range only (pilot 9000–9999). Run headers carry no stage. The shared run store means a confirmatory view **reuses** any matching run, including one first produced by an exploratory config (for example, `secondary.yaml`'s comparator cells, ρ ∈ {0, 1}, seeds 0–29, if run before `confirmatory.yaml`). The protocol is identical, but this breaks the invariant as written | Mine (shared store) | S: stamp the role in the header; confirmatory refuses others |
| V6 | #9 Frozen analysis | Analysis code is frozen and **hashed** at pre-registration; the hash goes in Stage 4 manifests | Constants are frozen in `sas/prereg.py`. There is no code hash and no check | Gap | S |
| V7 | #1 Response bank | Completions come from a hashed bank built offline (one per task, by a worker model); objections from 2–3 length- and tone-matched variants per family, assigned at random | No bank. One objection template per family, with no variants; completions have no text | Mine (DEVIATIONS A3) | M (`sas bank build` is a live, one-off step) |

## 2. Contradictions with PRD functional requirements

| ID | PRD ref | PRD | Harness | Source | Effort |
|---|---|---|---|---|---|
| F1 | FR4.1 | The coordinator sees the **last W = 15 rounds** of feedback (`feedback_window`) | The **full** history every round | Mine (DEVIATIONS A2: makes H3 information-matched) | S (config option). The Bayes baseline would need the same window to stay matched |
| F2 | FR4.2 | Decision via a **forced function tool** `assign_worker(worker_label: enum, notes ≤ 300 words)`, `tool_choice` named; JSON-in-text only as a fallback | JSON-in-text only | Gap | S–M; the probe must test whether forcing works (PRD §7.2) |
| F3 | FR4.2 | Notes ≤ **300 words** | ≤ **1,500 characters** (about 250 words), truncated | Mine | S |
| F4 | FR4.4 | Temperature default **0.7** | **1.0** in every config | Mine (DEVIATIONS B4) | S |
| F5 | §8 config | `max_output_tokens: 600` | 512 | Archive (512 was enough with reasoning off) | S |
| F6 | §8, §9 Stage 3 | `rounds: 40` | T = **60** | Review (research doc says 60; DEVIATIONS B1) | S. The PRD itself is split: §8 says 40, §10's cost model uses 60 |
| F7 | FR5.2 | `reason_visible` = outcome plus **the objection text** | Objection text **plus the task fact** (permission list or data value), so correctness is verifiable | Mine (review factor: "whether correct and unwarranted objections can be told apart") | S. **Open design question:** with text alone, objection wording is identical whether correct or not (or randomly varied, per FR3.2), so the PRD's condition cannot separate correct from unwarranted objections |
| F8 | FR5.2 | Audit feedback: "Audit: W3 proceeded on a task that required objection (−L)" | "completed; audit flagged a violation", points −30 net | Mine | S (wording only) |
| F9 | FR4.1 | Payoff rules include "the audit rule **if shown**", implying audit disclosure could vary | Audits are always disclosed; frequency never is | Mine | S if it becomes a factor |
| F10 | FR6.1 | Bayes keeps a posterior over **label-to-type assignments** (joint, which respects 2 of each type) and maximises Ũ "under the condition's payoffs" (reads as knowing ρ) | Primary H3 comparator is **ρ-uncertain** Bayes with an **independent** per-label type prior. ρ-known Bayes is kept as an upper bound | Review (fix 1.3) + mine (independent prior) | M: the joint label-to-type posterior is 8!/(2!⁴) = 2,520 assignments, tractable |
| F11 | FR3.2, FR2.3 | Task pools generated once per config and **hashed** | Tasks generated on the fly, deterministically from (seed, round); no pool file or hash | Mine | S |
| F12 | FR2.1 | Evidence task: a **small table plus a claim**, checked deterministically (for example, a computed growth rate vs threshold) | One measured value vs threshold | Mine (simpler) | M; extend `test_leakage` |
| F13 | FR2.2 | Title example "Data export request #0412" (minimal) | Descriptive titles ("Report whether North churn exceeded the target in Q2"). The leakage test passes; titles are drawn before θ | Mine | none needed unless the team prefers minimal titles |
| F14 | §3, H1 | H1 is **one-sided** | Two-sided bootstrap p (conservative) | Mine (PREREGISTRATION §5) | S |
| F15 | §3, H2 | **Logistic fit** of preference against ρ; empirical switch point vs ρ* | Paired contrast DiD(ρ_max) − DiD(ρ_min) as the test, plus an interpolated switch point with bootstrap CI | Review (§2 / B20) + mine | M |
| F16 | FR8.2 | **GEE logit is the primary model**; mixed logit with random intercepts for **run and label** as sensitivity | **Cluster bootstrap DiD is primary**; GEE (bias-reduced) supporting; mixed logit has a run intercept only | Mine (review 4.2 lists bootstrap first) | S to relabel; S to add the label intercept |
| F17 | FR8.2 | Holm correction **across model families** | A named family of 9 tests (H1, H2, H3 × 3 models), Holm together | Review §2 | S (both can be reported) |
| F18 | §9 Stage 4 | Confirmatory = the **full factorial** (ρ × feedback × c × π) × ≥ 3 families | Confirmatory = **core ρ sweep only** (ρ ∈ {0, .25, .5, 1}, c = 5, π = .25, outcome); full grid and secondary are **exploratory** | Review §2 (named family) | Config change; but Holm across 32+ cells costs power |
| F19 | §9 Stage 3 gate | Signal stage advances on **\|DiD\| ≥ 5 pp** or a visible Bayes–LLM gap | The pilot **masks DiD, H3, λ̂ and shares** (only checklist items 1–2) | Review (fix 1.1) | S. **Direct conflict:** PRD rule 1 already keeps Stage 3 data out of Stage 4, so the PRD intends DiD to be visible at Stage 3 |
| F20 | §9 Stage 3 | **2 cheap models**, ρ ∈ {0, 1}, outcome-only, 10 runs × **40** rounds | Pilot: **3 models** (including glm-5.2, the most expensive), 10 runs × 60 rounds, seeds 9001–9010 | Mine | S |
| F21 | §1 and §9 rule 4 | A null on H1 is reportable only if the positive control passes **and** TOST rejects ≥ 5 pp | The family verdict uses TOST but **does not check the positive control**; the report shows it next to item 1 | Gap | S |
| F22 | NFR cost | Hard budget **per invocation**; abort when **projected** spend exceeds it | Cumulative cap **per experiment ledger**; checked against *spent*, not projected, before each call | Mine | S |
| F23 | FR1.4 | Exponential backoff with jitter on **429** and 5xx | 5xx: backoff with jitter (matches). 429: a global 60 s pause (or Retry-After) and the rate halved; stop after 3 cycles | Archive lessons | S (keep the gate, add jitter) |
| F24 | NFR concurrency | "Runs are independent, with no shared state" | Runs share one rate gate and the run store (no shared *model* state) | Mine | none needed (probably within intent) |

## 3. Missing PRD features

| ID | PRD ref | Missing | Effort |
|---|---|---|---|
| M1 | FR3.2, §4, CLAUDE | `sas bank build`: the offline worker response bank (see V7) | M |
| M2 | FR1.1, FR1.3, FR1.6 | A `Provider` protocol (`complete(CompletionRequest) -> CompletionResult`) and a scriptable `MockProvider` returning pre-set decisions; an optional OpenAI-compatible provider. Now: `AdaptionClient` plus `FakeClient`/`FlakyFakeClient` (a softmax-λ policy) with an ad-hoc interface | M |
| M3 | FR8.5, §9 Stage 0 | **Parameter recovery gate**: plant λ and an effect in the mock and run the full pipeline 100 times; the 95% CI must cover the DiD in ≥ 90%. Now: only a point check that λ̂ recovers a softmax baseline's λ | M (cheap to run: offline) |
| M4 | FR8.3 | **Manipulation check**: at ρ = 1, a detected violation lowers the offending label's next-round assignment probability | S |
| M5 | FR8.3 | Leakage test as **AUC with CI includes 0.5**. Now: naive-Bayes accuracy vs majority, binomial test (equivalent intent). No `tests/test_leakage.py` by that name | S |
| M6 | FR8.3, CLAUDE | Protocol-failure **rate < 2% per run** as a validity check, and a report that **fails loudly** on any failed check. Now: runs with > 10% fallbacks are excluded, and checks are reported, not enforced | S |
| M7 | FR9.2 | Exploratory reports watermarked **"EXPLORATORY — not confirmatory"** | S |
| M8 | §9 Stage 1 | **Smoke stage**: 1 model × 3 runs × 10 rounds live; gate on parse rate ≥ 98%, leakage, measured cost, §7.2 items. Now: `probe_models.py` does 6 calls per model on real prompts (parse, reasoning control, temperature accepted). No forced-tool check, cost gate or parse-rate gate | S–M |
| M9 | §9 Stage 2 | **Pilot C**: one-shot paired choices, careful vs complier with matched histories, about 200 pairs per model; sets the H1 prior and calibrates λ for power | M |
| M10 | FR8.4 | `sas power` over a **(λ, π, ρ) grid** targeting **80% power for DiD = 10 pp**. Now: `power_sim.py` varies the learner and n at π = 0.25, using each learner's own DiD (about 7–14 pp), and adds TOST power | S |
| M11 | FR1.5, §11 | Record **cached tokens** and check they don't differ by condition | S |
| M12 | FR1.2, §7.1 | Use the **`adaption` SDK** (`client.responses.create`); `sas models` lists hosted models. Now: raw `httpx` POST (request shape matches §7.1); no model listing | S–M |
| M13 | FR7.1 | Typed event stream (`run_start`, `round_start`, `coordinator_call`, `assignment`, `worker_action` with `bank_item_id`, `audit`, `feedback_shown`, `score_update`, `notes_update`, `protocol_failure`, `run_end`), with `schema_version`. Now: one record per round, plus `resume` events | M |
| M14 | FR1.5, CLAUDE | Prices in `configs/pricing.yaml`. Now: hard-coded `PRICES` in `sas/adaption.py` | S |
| M15 | FR3.4, §11 | Never mix model versions within a cell; re-run Stage 1 on any change. Now: the served model is recorded and a mix is *warned* about, not refused | S |

## 4. Structural and naming differences

| ID | PRD / CLAUDE.md | Harness |
|---|---|---|
| N1 | `src/sas/` package with `providers/ tasks/ workers/ coordinator/ baselines/ sim/ logging/ analysis/ cli.py` | Flat `sas/` modules plus `scripts/*.py` |
| N2 | `sas` CLI: `models`, `bank build`, `estimate`, `run`, `analyze`, `report`, `power`, `recover` | Separate scripts: `run_experiment.py` (with `--dry-run` = estimate), `run_baselines.py`, `build_dataset.py`, `analyze.py`, `figures.py`, `report.py`, `power_sim.py`, `probe_models.py`, `leakage_check.py` |
| N3 | `configs/experiments/{mock,smoke,pilot_c,signal,confirmatory}.yaml`; config keys `stage`, `coordinator.*`, `workers.*`, `tasks.*`, `rounds`, `runs_per_cell`, `analysis.*`, `budget.*`, `seed` | `configs/{smoke,pilot,confirmatory,full_grid,secondary}.yaml`; keys `role`, `models`, `llm.*`, `factors`, `seeds`, `seeds_by_cell`, `T`. Factor level `outcome` vs PRD `outcome_only` |
| N4 | `data/runs/<group>/<run_id>/{events.jsonl, manifest.json}`; derived **parquet** | `results/runs/<coordinator>/<cell>/<fingerprint>/seed<N>.jsonl`; derived **CSV** |
| N5 | Randomness from a config `seed` plus run index | Run seed alone (common random numbers across cells and coordinators). Same purpose; FR6.4 pairing holds |
| N6 | Conventions: `ruff` + `pyright` strict on sim/analysis; dataclasses or pydantic for every event and config; pure functions in `sim/` and `analysis/`, I/O only in cli/logging/providers | No ruff or pyright configured. Events are dicts. `sas/grid.py` mixes config, storage and I/O |
| N7 | Doc filenames | `docs/PRD (1).md` and `docs/CLAUDE (1).md`. CLAUDE.md expects `DEVIATIONS.md` at the repo root; the harness has `docs/DEVIATIONS.md` |

## 5. Things the harness adds beyond the PRD (for awareness, not deviations)

- **Reasoning disabled** (`reasoning: none`, verified per response). The PRD
  only lists reasoning-token inflation as unverified (§7.2).
- **Behaviour-fingerprint cache key, per-round checkpoints and resume**, a
  circuit breaker, and uncertain-charge accounting for 504s.
- **Common-random-number tapes** shared across cells and coordinators.
- **Random objector re-matched at every π.** The PRD's FR3.1 formula already
  implies this.
- **Secondary conditions:** qualitative framing and preachy tone (PRD:
  task-visible only).
- **Softmax-λ baseline.**
- **Replay audit, script-fidelity and position-bias checks, a
  differential-fallback test, and the O-routing measure** for the
  task-visible condition.

## 6. Where the sources disagree (needs a decision, not just alignment)

1. **Pilot masking (F19)** vs PRD Stage 3's DiD gate.
2. **Scope of the confirmatory family (F17, F18):** the external review's
   named core family vs the PRD's full factorial with Holm across model
   families.
3. **H3 comparator (F10):** ρ-uncertain Bayes (external review) vs the PRD's
   reading, which knows ρ.
4. **T (F6):** 60 (research doc) vs 40 (PRD config).
5. **Reason-visible content (F7):** objection text alone (PRD) can't separate
   correct from unwarranted objections, which is what the review says this
   factor tests.
6. **Imputation (V1):** CLAUDE.md forbids it outright.

`docs/DEVIATIONS.md` says the B = 5,000 and two-re-ask choices were
"unverified" against the PRD. Both now match it, but the fallback that
follows the re-asks does not (V1).
