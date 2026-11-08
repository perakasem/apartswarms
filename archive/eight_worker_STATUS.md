# Selection Against Safety: publication status

Snapshot: **2026-11-08 02:13 UTC** (2026-11-07 21:13 America/Toronto).

The synthetic baseline collection is complete. All three models passed one-round Adaption smoke checks. The larger one-shot preference pilot recorded **50 valid choices out of 96 planned cases** before a request-budget interruption. **No output from the planned replicated 60-round LLM study was found in the inspected results.** These records do not yet establish selection against safety in LLM coordinators.

Read the [simplified paper](eight_worker_SIMPLE_PAPER.md) or its [PDF](eight_worker_SIMPLE_PAPER.pdf) for an explanation of the question, method, results, and limits. This is the separate eight-worker experiment; it does not alter or combine the repository's completed four-worker studies.

## Completed checks and collection coverage

| Component | Observed status | Interpretation |
|---|---|---|
| Synthetic baselines | 1,920 completed episodes; 115,200 rounds; 32 conditions x 3 scripted coordinators x 20 environment seeds | Simulation benchmarks, not LLM observations |
| Revised smoke test | 3/3 completed one-round decisions | API connectivity and readable output on these three calls |
| One-shot preference pilot | 87 logged cases: 50 valid and 37 invalid; 9 further cases unrecorded | Incomplete exploratory collection; no preference-effect estimate published here |
| Repeated live pilot | No output directory found at this snapshot | No completed repeated-allocation LLM result available for this report |
| Software validation | 55 tests passed; all baseline round fields reproduced except run IDs and prompt-version labels | Implementation checks, not successful hypothesis tests or human scientific review |

## Preference-pilot cases by model

| Model identifier | Planned | Logged | Valid choices | Invalid cases | Unrecorded |
|---|---:|---:|---:|---|---:|
| `deepseek-v4-flash` | 32 | 32 | 30 | 2 cases ending in HTTP 504 failure | 0 |
| `gemma-4-26b-a4b-it` | 32 | 32 | 0 | 32 JSON-parsing failures | 0 |
| `qwen3.8-27b` | 32 | 23 | 20 | 3 cases ending in HTTP 504 failure | 9 |
| Total | 96 | 87 | 50 | 37 | 9 |

Logged cases are not necessarily valid decisions. In particular, Gemma's provider responses were marked completed, but the recorded content did not pass the pilot's decision parser. This is an integration failure, not evidence of unsafe worker selection. The interruption ledger reports request-budget exhaustion. A case can consume multiple API requests through retries; failure counts here describe logged cases, not total HTTP attempts. The nine unrecorded cases are all Qwen cases. The case grid covers four audit probabilities, two feedback conditions, two environment seeds, and two order presentations for each model.

The earlier publication snapshot counted 82 **logged cases**; it did not establish 82 valid choices. This update makes validity and missingness explicit. Logs alone do not establish whether a process is currently active.

## Prompt versions and interpretation

The original smoke test completed DeepSeek and Gemma decisions, while Qwen exhausted a 1,024-token limit without a final answer. Version 2 raised the shared cap to 8,192 tokens and clarified that an objection ends the task without a completion reward. All three revised one-round checks completed. The version-1 smoke observations are not combined with version-2 experimental observations; see the [amendment](eight_worker_AMENDMENT_V2.md).

The [baseline results](eight_worker_BASELINE_RESULTS.md) show consequences of the specified completion reward, objection cost, and incomplete auditing. They do not establish spontaneous safety aversion, an isolated causal objection penalty, or real-world prevalence. The five-round contrast changes task type, which also changes scores, completions, audits, and evidence. Thompson sampling is a learning heuristic rather than a guarantee of optimal behavior. Allocation-weighted expected risk and actual finite-sample violations are distinct quantities.

## Remaining work

Resolve the invalid-output and budget interruptions under a documented protocol amendment before further live collection. Retain the current failures and cost records. The existing one-shot resume behavior skips already logged failed cases; rerunning the same command does not repair their missing choices. Complete and validate replicated 60-round trajectories, report failures by model and condition, and compare with matched synthetic baselines. No further inference calls were made to prepare this paper or status update.

## Evidence

The [sanitized execution snapshot](eight_worker_execution_snapshot.json) records coverage and source-file hashes. It was prepared from smoke summaries, preference-case metadata, the interruption ledger, and baseline analysis. It includes no credentials, personal filesystem paths, prompts, or raw model reasoning. The archived baseline collection remains unchanged. Use this status file for the updated live-collection snapshot; the source archive preserves the earlier dated publication snapshot.
