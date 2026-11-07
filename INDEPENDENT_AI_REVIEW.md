The completed paced study does not show a clear loss of focal work after credit for a correct objection. It also does not show a clear increase in team violations from that credit cue. This result does not prove that the effects are zero.

I checked all 160 main result records. Each run has 24 valid assignments. The sample has 3,840 valid assignments, 40 complete seed pairs per model, and no missing main pairs. The records use only main seeds 2001–2040. The earlier stopped main batch is not part of this sample.

The primary difference is worker-credit share minus checker-credit share. Shares use all 24 scheduled slots. I calculated focal shares from the saved assignment counts. I then rebuilt the paired means, 10,000-sample bootstrap intervals, permutation values, and Holm adjustment. They agree with analysis.json, within floating-point precision. I did not use the study analysis functions for these checks.

| Model | Focal share: worker credit | Focal share: checker credit | Paired difference | 95% interval | Holm-adjusted p |
|---|---:|---:|---:|---:|---:|
| Qwen 3.5 397B | 39.48% | 40.31% | −0.83 points | −8.75 to +6.15 points | 0.8530 |
| GLM 5.2 | 37.92% | 32.50% | +5.42 points | −6.25 to +17.08 points | 0.7731 |

The unadjusted permutation values are 0.8530146985 for Qwen and 0.3865613439 for GLM. There are 25 zero-difference pairs for Qwen and 23 for GLM. Neither bootstrap interval is flagged as constant.

I also rebuilt each secondary paired mean and interval. These agree with the saved analysis.

| Model | Measure | Worker credit | Checker credit |
|---|---|---:|---:|
| Qwen | Total careful-worker share | 88.96% | 85.31% |
| Qwen | Violations on tasks requiring an objection | 43/480 = 8.96% | 40/480 = 8.33% |
| GLM | Total careful-worker share | 85.63% | 86.25% |
| GLM | Violations on tasks requiring an objection | 43/480 = 8.96% | 48/480 = 10.00% |

The paired violation difference is +0.63 points for Qwen, with an interval from −1.25 to +2.71 points. It is −1.04 points for GLM, with an interval from −2.50 to +0.42 points. Both intervals include zero. These are secondary measures.

Careful-worker share increased from the first eight tasks to the last eight tasks in all four model-condition groups. The increases were 15.00–20.31 percentage points. This is a descriptive result. It does not show the proposed gradual loss of work for careful workers in this task setting. It does not establish why the coordinator changed its choices.

Two secondary intervals for the difference in that increase exclude zero. They have opposite directions across models. Do not present them as confirmation of selection against safety. Both models increased careful-worker share in both conditions. These secondary comparisons also lack the primary tests' adjustment across the full set of secondary measures.

The data still contain task violations. Do not describe the teams as perfectly safe. Also, do not treat these synthetic violation rates as estimates for real organizations.

The final claim should remain narrow. The treatment changes one initial credit field. It does not randomly vary every later objection. It can change beliefs about worker ability and the number of mentions of the focal ID. A focal loss would not alone establish team harm, because work could move to the other careful worker.

Only the coordinator is a live model. Worker behavior is fixed. Rules and audits are explicit. Time and cost are equal by design. The study supplies the coordinator role and therefore does not test how a hierarchy forms. It tests hosted deployments with reasoning effort set to none. The deployment revision is not pinned.

Use uncertainty wording in the final report: "We did not find clear evidence of selection against the worker after this credit cue." Avoid: "The experiment proves that selection against safety does not occur." The primary intervals still permit both negative and positive effects of practical interest.

Files checked: PACED_PROTOCOL.md, results/live_paced/study.json, results/live_paced/results.json, and results/live_paced/analysis.json. This review checks aggregation and interpretation. It does not replace the separate raw-log and accounting audit. No paid calls or frozen-file changes were made.
