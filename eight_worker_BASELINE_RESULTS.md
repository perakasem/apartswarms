# Selection Against Safety: synthetic baseline results

**These are synthetic simulation results. No LLM coordinator generated the allocations summarized below.** The completed baselines check the implementation and quantify the behavior induced by the declared incentives. They are not evidence that real LLM coordinators exhibit the proposed failure.

This document covers the separate eight-worker experiment under `experiments/selection-against-safety/` inside the source archive, not the repository's existing four-worker studies.

## Completed design

| Item | Completed coverage |
|---|---|
| Worker pool | Eight workers with immutable response policies: two careful, two compliers, two over-refusers, two rate-matched random objectors |
| Synthetic coordinator policies | Uniform random selection; oracle maximizing true expected score; Bayesian Thompson sampling maximizing perceived score |
| Audit probability ρ | 0, 0.25, 0.5, 1 |
| Objection friction c | 5, 15 points |
| Objection-required probability π | 0.15, 0.35 |
| Feedback | Outcome only; objection reason visible |
| Fixed payoffs | Completion value v = 10; violation loss L = 40 |
| Replication | 20 environment seeds per condition and policy; 60 rounds per run |
| Total | 32 conditions × 3 policies × 20 seeds = 1,920 completed runs; 115,200 allocation rounds |
| Analysis | Next-five-round horizon; 1,000 bootstrap resamples; bootstrap seed 1729; zero incomplete runs excluded |

The same environment seeds are reused across policies and conditions. The full total is not a count of 1,920 mutually independent observations; uncertainty is resampled across the 20 runs within each condition. Workers remain fixed, so only allocation changes across rounds.

## Main benchmark example

The following transparent slice fixes c = 5, π = 0.35, outcome-only feedback, v = 10, and L = 40. It includes every tested audit probability for the Bayesian policy. Uniform and oracle entries use ρ = 0.25; their allocation rules do not respond to audit feedback. Each row contains 20 runs. Brackets are unadjusted 95% percentile run-bootstrap intervals.

| Coordinator | Audit ρ | Careful share, late − early (pp) | Late careful − complier share (pp) | Expected violation risk | Realized violation rate |
|---|---:|---:|---:|---:|---:|
| uniform | 0.25 | 0.7 [-5.0, 6.8] | 2.0 [-4.2, 8.8] | 15.8% [15.2, 16.4] | 14.5% [12.7, 16.2] |
| oracle | 0.25 | 0.0 [0.0, 0.0] | 100.0 [100.0, 100.0] | 3.5% [3.5, 3.5] | 3.0% [2.0, 4.1] |
| bayesian | 0 | -14.5 [-21.8, -7.3] | -67.5 [-82.0, -50.7] | 23.0% [21.1, 24.7] | 21.9% [19.3, 24.4] |
| bayesian | 0.25 | -12.0 [-17.5, -6.0] | -73.2 [-82.8, -63.2] | 24.0% [22.7, 25.3] | 23.2% [20.6, 25.9] |
| bayesian | 0.5 | 21.8 [12.2, 31.5] | 43.2 [32.0, 55.2] | 11.1% [10.0, 12.1] | 10.1% [8.4, 11.9] |
| bayesian | 1 | 28.7 [17.2, 38.0] | 57.0 [42.7, 69.2] | 9.9% [8.9, 11.0] | 8.6% [7.0, 10.5] |

“Early” is rounds 1–20 and “late” is rounds 41–60. Share differences use percentage points (pp). Expected violation risk is computed from assigned policy recall and the task distribution; realized rate counts actual simulated violations. The zero-width oracle intervals for allocation quantities reflect its fixed choice of careful workers, not perfect empirical knowledge about deployed systems.

In this slice, Bayesian Thompson sampling shifts assignments toward compliers at low audit rates and toward careful workers at higher audit rates. At ρ = 0.25, careful share falls by 12.0 percentage points from early to late, and expected violation risk averages 24.0%. At ρ = 0.5, careful share rises by 21.8 points and expected risk averages 11.1%. These changes are consistent with the score-based ranking reversal; they do not establish an LLM effect.

## Friction and the predicted threshold

For careful and complier policies with equal false-objection rates, the perceived-score difference is:

$$\widetilde U_K-\widetilde U_C=\pi(r_K-r_C)(\rho L-v-c).$$

The ranking changes at ρ* = (v + c)/L: 0.375 for c = 5 and 0.625 for c = 15. The table holds π = 0.35 and outcome-only feedback fixed and reports the late careful-minus-complier assignment share for the Bayesian baseline.

| Friction c | Predicted ρ* | ρ = 0 | ρ = 0.25 | ρ = 0.5 | ρ = 1 |
|---:|---:|---:|---:|---:|---:|
| 5 | 0.375 | -67.5 [-82.0, -50.7] | -73.2 [-82.8, -63.2] | 43.2 [32.0, 55.2] | 57.0 [42.7, 69.2] |
| 15 | 0.625 | -67.5 [-81.5, -49.5] | -73.2 [-83.0, -63.2] | -84.5 [-91.2, -76.2] | 57.0 [44.0, 70.5] |

Values are percentage points with 95% run-bootstrap intervals. The four audit levels bracket the predicted change; they do not estimate a precise empirical switching point. A finite-horizon learning policy need not switch exactly at the full-information algebraic threshold.

## Task-type interaction

The event contrast compares the selected worker’s share of the next five assignments after an objection-required task versus a permissible task, and subtracts the complier contrast from the careful-worker contrast. The analysis pools eligible event-cell totals and bootstraps whole runs, preserving overlap between future windows.

| Bayesian audit ρ | Task-type interaction (pp), c = 5, π = 0.35, outcome-only |
|---:|---:|
| 0 | -11.0 [-17.7, -4.7] |
| 0.25 | -12.9 [-19.9, -4.7] |
| 0.5 | 2.4 [-2.5, 7.8] |
| 1 | 9.4 [4.1, 15.0] |

This is a task-type interaction, not an isolated causal objection effect: the randomized task also changes completion, score, audit outcomes, and reasons. The oracle never assigns compliers, so its corresponding contrast is not estimable; missing comparison cells are not treated as zero.

## What the simulation does and does not show

The results validate the proposed incentive channel in a controlled model. When only detected violations are penalized, maximizing visible score can favor unsafe completion. The oracle maximizes true score with privileged knowledge; the Bayesian comparator learns from the specified observation channel. Thompson sampling is a particular heuristic, not a finite-horizon optimality guarantee.

The expected-risk identity is π times the assignment-weighted probability of proceeding on an objection-required task. It is an expectation, not an exact equality for realized finite samples. Expected risk is mathematically linked to the assignment shares and is not an independent replication of the allocation finding.

The intervals are descriptive and unadjusted across the many cells and metrics. These outputs do not implement confirmatory Holm testing, mixed-effects inference, or equivalence testing. A confidence interval containing zero is not evidence of absence. The displayed slice is illustrative; the full analysis contains all 96 policy-by-condition summaries.

## Analysis provenance

Numerical source: `baselines_verified_v1/analysis/analysis.json` (`n_runs = 1920`, `n_records = 115200`). The preserved analysis source SHA-256 is `c2b3ed81cdb4a72b751719a705c2f7d2c2a1db63bd887edf9f3c63405fdf6ef2`.

Published companion outputs include the [full results table](eight_worker_RESULTS.md), [condition-level metrics](eight_worker_condition_metrics.csv), [run-level metrics](eight_worker_run_metrics.csv), [audit-risk figure](eight_worker_audit_risk.svg), and [provenance](eight_worker_provenance.json). Raw baseline trajectory logs are regenerated using the commands in [README.md](eight_worker_README.md). See [STATUS.md](eight_worker_STATUS.md) for the separate status of live Adaption inference.
