# Follow-up results: repeated safety notices and audit timing

The follow-up is complete. It did not establish the predicted loss of careful-worker assignments after worker-attributed safety notices. Qwen's estimate was in the opposite direction. GLM's assignment estimate was small. GLM's full safety claim cannot be assessed for all planned seeds because some risky outcomes are unknown.

All 320 main runs finished. The study used 40 fresh seeds per model, with four matched conditions per seed. Each run had 24 free choices. The first 18 choices formed the primary window. Nine tasks in that window required a hold. Forced exposure records were excluded from all scored assignments and violations.

The four conditions crossed notice source (WORKER or NOTIFIER) with audit timing (immediate or delayed). NOTIFIER only relayed the worker's notice; it did not verify it. Both careful workers received the notice-source treatment. Task facts stayed private until audit release. The two careful and two shortcut workers kept fixed local rules. All workers had equal stated cost, time, and skill on permitted tasks. Careful workers made no unnecessary refusals.

The primary contrast is **worker_delayed minus notifier_delayed**, or C minus D. A negative assignment effect would support the predicted selection penalty. A positive risky-task violation effect would support its proposed safety cost. The independent analysis unit is a matched task seed, not an individual choice.

| Hosted model | Careful-worker share effect | 95% paired bootstrap interval | Primary pairs | Risky-task violation effect | 95% paired bootstrap interval | Risk pairs |
|---|---:|---:|---:|---:|---:|---:|
| `qwen3.5-397b` | +3.47 points | +0.56 to +6.53 | 40/40 | -3.33 points | -7.22 to +0.28 | 40/40 |
| `glm-5.2` | +0.28 points | -0.83 to +1.39 | 40/40 | -0.69 points | -1.74 to 0.00 | 32/40 |

All values are percentage points. The intervals use 10,000 paired bootstrap samples. The planned one-sided tests looked for less careful work and more violations. The two-model Holm-adjusted primary, risk, and joint p values were all 1.0.

For Qwen, the careful-share interval is positive. This is a pattern opposite to the predicted penalty. It does not conflict with the negative-direction test result. We did not add a new opposite-direction test after collection. Treat a possible assignment benefit as an exploratory finding that needs a new test.

The full safety-failure rule required both predicted directions and all three adjusted test criteria. Qwen did not meet that rule. GLM also lacked a complete risk result for eight planned delayed-condition pairs. Its full-sample claim is therefore marked `not_assessable_for_full_planned_sample`, rather than a clean null safety result.

![Follow-up paired effects](followup_effects.png)

*The left panel uses all 40 assignment pairs per model. The GLM risk panel uses 32 complete pairs. Unknown risky outcomes are not counted as safe. The intervals in this figure are not multiple-test-adjusted intervals; the saved adjusted tests determine the planned decisions.*

**Invalid choices and missing safety outcomes**

Qwen made 3,840 valid main choices and no invalid main choice. GLM made 3,816 valid main choices and 24 invalid main choices. Across GLM's four conditions, 12 primary risky outcomes were unknown. All main runs still processed their 24 scheduled slots.

An invalid choice makes no assignment. It remains in the work-share denominator. An invalid risky choice makes the run's risk point unknown. No format-repair call was made, and no invalid choice was removed from the saved record.

GLM's delayed primary counts show why its small assignment gap needs care:

| Notice source under delayed audit | Careful assignments | Shortcut assignments | Invalid slots | Total scheduled slots |
|---|---:|---:|---:|---:|
| Worker | 707 | 5 | 8 | 720 |
| Relay | 705 | 5 | 10 | 720 |

The two-slot careful-work difference equals the two-slot invalid-output difference. Shortcut assignments were equal. This is an accounting observation, not a replacement measure or a new test of preference.

For GLM, the risk contrast over all 40 planned seeds is bounded by **-2.22 to +0.28 percentage points**. These bounds allow each unknown risky outcome to be either safe or a violation. They are bounds for the saved sample, not confidence limits for a wider population. The complete-pair interval and these bounds answer different questions.

**What changed with audit timing**

| Model | Worker, immediate | Relay, immediate | Worker, delayed | Relay, delayed |
|---|---:|---:|---:|---:|
| Qwen: primary careful-worker share | 96.39% | 95.56% | 87.22% | 83.75% |
| GLM: primary careful-worker share | 99.86% | 99.58% | 98.19% | 97.92% |

Qwen selected fewer careful workers in the delayed-audit conditions. This is a descriptive condition comparison. It was not the primary test. The planned careful-share interaction, `(C-D)-(A-B)`, was +2.64 points for Qwen, with an interval of -0.56 to +5.97. It was 0.00 points for GLM, with an interval of -1.11 to +1.11. These supporting intervals were not adjusted for multiple comparisons.

Careful-worker share generally increased across Qwen's first three blocks. GLM's shares stayed near 100%. The data do not show careful workers becoming progressively irrelevant in this task setting.

![Careful-worker share across blocks](followup_blocks.png)

*All pending audits were released before choice 19. The last six choices are a descriptive recovery check. The release time was fixed, so a before/after change does not separately identify the effect of audit release.*

**Completion and checks**

The study made **8,072 new paid calls**: eight probes, 384 pilot choices, and 7,680 main choices. All probes were valid. The pilot had 383 valid choices and one invalid choice, and passed its fixed technical gate. There were no transport retries, new unknown charges, or rate-limit cycles.

Before paid calls, **138 offline tests passed with socket connections blocked**. The complete local pipeline passed all 8,072 simulated calls. Native tokenizer checks covered 24,768 prompt contexts per model. Every live request also received an input count before dispatch.

The final record audit passed with no issues. It checked all 338 runs, 8,072 requests and outcomes, source copies, linked logs, scores, audit timing, hidden facts, cost history, and authorization. All 8,072 response IDs were unique. Every response confirmed reasoning effort `none` and reported zero reasoning tokens. No input or output exceeded its fixed limit.

A separate program recomputed the main counts, paired effects, intervals, directional tests, joint adjustments, CSV values, and chart hashes. It imported no frozen scorer module. That review passed. Additional checks covered invalid outcomes and the full-claim rule. Both charts passed an AI display review. These checks do not imply human scientific review.

**Costs and limits**

| Cost scope | Estimated charge | Unknown-charge reserve | Total commitment |
|---|---:|---:|---:|
| Earlier work, carried | 9.15338335 | 9.61128000 | 18.76466335 |
| New follow-up | 15.19253195 | 0 | 15.19253195 |
| All studies | 24.34591530 | 9.61128000 | 33.95719530 |

All amounts are Adaption credits. No pending reserve remains. New cost stayed within **70 credits**. The combined commitment stayed within **100 credits**. All earlier unknown-charge reserves remain included. The unused amounts under those limits are 54.80746805 new-study credits and 66.04280470 global credits.

These are local token-cost estimates and retained reserves, not verified account deductions. This runner made no OpenRouter calls. Its OpenRouter spend was CAD$0. The budget record covers 13,052 attempts across all studies; only the new main sample enters this follow-up analysis.

**Scope and files**

The result concerns notice attribution and audit timing in a fixed worker pool. It does not prove that selection against safety is absent elsewhere. Workers did not learn, negotiate, or form roles. Forced exposures kept all workers visible. Runs were short. Notice source could change beliefs or attention. The exact hosted model revision was not independently verified.

Read the [full report](followup_REPORT.md), [fixed protocol](FOLLOWUP_PROTOCOL.md), [effect table](followup_paired_effects.csv), [condition means](followup_condition_means.csv), [seed contrasts](followup_seed_contrasts.csv), [audit](followup_audit.json), and [separate numerical review](followup_independent_numeric_review.json).

The [complete follow-up archive](followup-full-results.zip) contains raw records, frozen source and tests, cost-history records, charts, and an offline verifier. Root files use the `followup_` prefix. Files inside the archive keep their original study paths. Extract the ZIP into a new folder and run `python3 reproduce_followup.py` with Python 3.13. The verifier uses no network connection and makes no model calls.

The [initial study paper](INITIAL_STUDY_PAPER.md) and its [PDF](INITIAL_STUDY_PAPER.pdf) describe the earlier, separate experiment. Its raw records remain in [full-results.zip](full-results.zip). The two studies must not be combined into one scientific sample.
