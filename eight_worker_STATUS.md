# Selection Against Safety: publication status

Snapshot: **2026-11-08 00:59 UTC** (2026-11-07 19:59 America/Toronto).

The synthetic baseline study is complete. Adaption inference has been verified on three model families, and a one-shot preference pilot has partial results. **No completed, replicated 60-round LLM study is available in the inspected outputs at this snapshot.** The available results do not yet establish selection against safety in LLM coordinators.

This is the separate **eight-worker Selection Against Safety experiment** under `experiments/selection-against-safety/` inside the source archive. Its scope and status must not be conflated with the repository's existing four-worker studies or their completed results.

## Evidence available

| Component | Verified status | What it establishes |
|---|---|---|
| `baselines_verified_v1` | 1,920 completed synthetic runs; 115,200 rounds; 32 experimental cells × 3 scripted coordinators × 20 environment seeds | The environment and analysis pipeline execute, and the declared scoring incentives produce the expected comparison behavior. These are simulation results, not LLM measurements. |
| `live_smoke_v2` | 3 of 3 one-round API checks completed using prompt version `selection_safety_v2` | Adaption can return a valid worker-selection decision for each tested model. One round cannot measure allocation drift or the next-five-round estimand. |
| `preference_v2` | 82 logged one-shot matched-history decisions using prompt version `v2`; partial dataset | Preliminary model choices exist. This is an exploratory preference pilot, not the repeated-allocation experiment. No outcome claim is made from the partial sample here. |
| Original `live_smoke` | 2 of 3 one-round checks completed; one Qwen run stopped after two invalid decisions | An earlier integration issue occurred and is retained in the execution record. This prompt version is separate from the successful v2 checks. |

## Adaption models and latest coverage

| Model identifier | v2 API check | Logged preference-pilot decisions |
|---|---:|---:|
| `deepseek-v4-flash` | 1/1 completed | 32 |
| `gemma-4-26b-a4b-it` | 1/1 completed | 32 |
| `qwen3.8-27b` | 1/1 completed | 18 |

The pilot records observed at this snapshot span audit probabilities 0, 0.25, 0.5, and 1; outcome-only and reason-visible feedback; environment seeds 0 and 1; and both worker-order presentations. Counts above are logged decisions, not independent repeated trajectories. The snapshot does not assert whether a process remains active or whether later results exist.

## Claims suitable for the current release

The implementation holds worker response policies fixed, randomizes anonymous labels and presentation order, keeps current task truth hidden at allocation time, and records programmatic ground truth. It supports uniform, oracle, and Bayesian Thompson-sampling comparators, along with an Adaption coordinator and run-level uncertainty analysis. See [BASELINE_RESULTS.md](eight_worker_BASELINE_RESULTS.md) for numerical simulation results and [the full baseline table](eight_worker_RESULTS.md) for all conditions.

The baseline results demonstrate the consequences of a specified completion reward, objection cost, and incompletely audited violation penalty. They provide a benchmark for testing LLM coordinators; they do not establish spontaneous safety aversion, a pure causal objection penalty, or real-world prevalence.

## Remaining empirical work

1. Finish and validate the one-shot pilot, reporting malformed decisions and missing cases by model and condition.
2. Run replicated 60-round LLM trajectories with a frozen, documented protocol and source snapshot; retain incomplete-run status, including failures before the first logged outcome.
3. Compare each model with the baseline under matched experimental conditions and common environment seeds. Report paired uncertainty while recognizing that different allocators observe different histories.
4. Distinguish exploratory pilots from any later confirmatory design. Report all tested conditions and failures, rather than selecting only favorable findings.

## Interpretation notes

- The five-round contrast estimates a differential response to randomized task type. Task type changes objection, completion, score, audit results, and reasons; it does not isolate the effect of a correct objection alone.
- Thompson sampling is a Bayesian learning heuristic. A difference from it is not proof of irrationality or bias beyond every rational information-use strategy.
- The allocation-weighted violation formula is an expectation. Realized violations fluctuate around it, and falling careful-worker share need not increase risk if equally high-recall over-refusers receive the assignments.
- Synthetic and live runs, and distinct prompt versions, must remain identifiable in every table. Three successful one-round checks are not three completed experiments.

## Provenance

This status was prepared from the baseline analysis JSON and manifest, the two smoke-test execution summaries and status records, and the preference pilot's logged metadata. It contains aggregate execution information only. Local filesystem locations, credentials, account details, prompts, raw model outputs, and private model reasoning are not included.
