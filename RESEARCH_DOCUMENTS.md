# Research documents and supporting records

Publication index, 8 November 2026 (UTC). This repository contains three completed four-worker studies and a separate eight-worker project. Samples, prompts, scoring rules, and cost records must not be pooled across these projects.

## Start with the completed prompt comparison

The completed prompt comparison tested whether reducing explicit safety guidance changed the effect of a worker's hold notice on subsequent worker selection. It includes 320 main runs, 40 matched four-condition sets per model, and 7,680 executable main choices. The planned primary and full safety-claim rules were not met for either model. Qwen showed a large general reduction in careful-worker selection under the reduced-guidance prompt; that is a separate result from a penalty against the worker sending the notice.

| Reader's need | Document |
|---|---|
| Plain-language findings | [Results summary](PROMPT_RESULTS_SUMMARY.md) |
| Technical appendix with exact prompts, methods, statistical rules, and result tables | [Appendix](APPENDIX.md) · [PDF](APPENDIX.pdf) |
| Original generated report | [Full report](prompt_REPORT.md) |
| Frozen protocol and exact design | [Protocol](PROMPT_COMPARISON_PROTOCOL.md) · [Design JSON](PROMPT_COMPARISON_DESIGN.json) |
| Definitions for the public data | [Data dictionary](DATA_DICTIONARY.md) |
| Reproduce the saved analysis without model calls | [Reproduction guide](PROMPT_REPRODUCTION.md) |
| Complete data, prompts, responses, source, and tests | [Full archive](prompt-full-results.zip) |

## Tables, figures, and checks

| Material | Files |
|---|---|
| Each main run and each matched contrast | [Main runs](prompt_main_runs.csv) · [Seed contrasts](prompt_seed_contrasts.csv) |
| Condition means and effect estimates | [Condition means](prompt_condition_means.csv) · [Paired effects](prompt_paired_effects.csv) · [Joint-test components](prompt_joint_components.csv) · [Block means](prompt_block_means.csv) |
| Machine-readable records | [Main results](prompt_results.json) · [Analysis](prompt_analysis.json) · [Claim tests](prompt_claim_tests.json) |
| Figures | [Effects](prompt_effects.png) · [Full-claim components](prompt_components.png) · [Selection by block](prompt_blocks.png); SVG editions have the same base filenames |
| Collection status and frozen settings | [Status](prompt_status.json) · [Study settings](prompt_study.json) · [Main freeze](prompt_main_freeze.json) |
| Record and archive integrity | [Final audit](prompt_audit.json) · [Archive verification](prompt_archive_verification.json) · [Saved manifest](prompt_manifest.json) |
| Independent numerical calculation | [Numerical review](prompt_independent_numeric_review.json) · [Reviewer test receipt](independent_prompt_review_checks.json) |
| Tests and input-length checks | [Offline tests](prompt_offline_test_report.json) · [Integration tests](prompt_offline_integration_report.json) · [Offline audit](prompt_offline_full_audit.json) · [Tokenizer verification](prompt_tokenizer_verification.json) |
| Derived-table and figure provenance | [Result-file provenance](prompt_result_files_provenance.json) |
| Excluded preliminary stages | [Probes](prompt_probes.json) · [Pilot](prompt_pilot.json); neither contributes to the main estimates |

The checks above are automated or AI-assisted. They do not imply human scientific review, verification of provider billing, or confirmation of the hosted model weights.

## Source files available for inspection

These root copies are byte-identical exports from the already published archive. They make the verification code easier to inspect. **Execute them from a clean extraction of `prompt-full-results.zip`, not from this flat repository root.** Their dependencies and frozen source tree live inside that archive.

| Source | Purpose |
|---|---|
| [reproduce_prompt.py](reproduce_prompt.py) | Portable archive verification and recomputation; blocks network access |
| [audit_prompt.py](audit_prompt.py) | Audit of saved logs, prompts, outcomes, source hashes, costs, and pacing |
| [independent_prompt_review.py](independent_prompt_review.py) | Separate numerical calculation without importing the frozen scorer |
| [build_prompt_result_files.py](build_prompt_result_files.py) | Rebuild result tables and figures in a separate working copy |
| [prompt_requirements.txt](prompt_requirements.txt) | Recorded package versions for the runner, analysis, tokenization, and charts |
| [Export verification](appendix_source_export_verification.json) | Archive-member names and hashes for these copies |

The archive includes the frozen `prompt_study` package and `tests_prompt` suite, the exact per-request messages and responses, the saved worker facts and choices, and earlier cost-carry evidence. Large tokenizer assets and model weights are omitted; the reproduction guide explains the asset manifests and optional tokenizer check. There is no need to make new paid inference calls to verify the saved analysis.

## Earlier completed studies

| Study | Main sample | Reading | Protocol, results, and full records |
|---|---|---|---|
| Initial worker-credit test | 160 runs; 40 matched pairs per model | [Paper](INITIAL_STUDY_PAPER.md) · [PDF](INITIAL_STUDY_PAPER.pdf) | [Protocol](PACED_PROTOCOL.md) · [Report](REPORT.md) · [Tables](paired_effects.csv) · [Audit](audit.json) · [Publication notes](PUBLICATION.md) · [Archive](full-results.zip) |
| Repeated notices and audit timing | 320 runs; 40 matched four-condition sets per model | [Summary](FOLLOWUP_RESULTS_SUMMARY.md) · [Reader report](FOLLOWUP_READER_REPORT.md) | [Protocol](FOLLOWUP_PROTOCOL.md) · [Report](followup_REPORT.md) · [Tables](followup_paired_effects.csv) · [Audit](followup_audit.json) · [Archive](followup-full-results.zip) |

[Exact earlier system prompts](SYSTEM_PROMPTS.md) and [design limits](DESIGN_LIMITS.md) explain their scope. The follow-up contains missing GLM safety outcomes; its reader report explains the full-sample bounds. Earlier records are preserved, not retrospectively repaired or incorporated into the prompt-comparison sample. Historical plans and amendments inside the archives describe their status at the time they were written.

## Separate eight-worker experiment

The eight-worker project has **completed synthetic benchmarks**, comprising 1,920 episodes and 115,200 assignments. Its live preference pilot is incomplete: the dated snapshot records 50 valid choices, 37 invalid cases, and nine unrecorded cases. The three one-decision smoke checks passed. No completed repeated 60-round live study is reported.

Read the [simplified paper](eight_worker_SIMPLE_PAPER.md), [technical appendix](eight_worker_APPENDIX.md), [methods](eight_worker_METHODS.md), [plan](eight_worker_PLAN.md), [prompt amendment](eight_worker_AMENDMENT_V2.md), and [execution status](eight_worker_STATUS.md). The [baseline report](eight_worker_RESULTS.md), [interpretation](eight_worker_BASELINE_RESULTS.md), [condition metrics](eight_worker_condition_metrics.csv), [run metrics](eight_worker_run_metrics.csv), and [source archive](eight_worker_source_and_baselines.zip) document that separate design. The appendix identifies the additional full synthetic records and analysis files.

## Integrity and scope of this update

[FILE_MANIFEST.json](FILE_MANIFEST.json) gives sizes, SHA-256 hashes, and Git blob hashes for root publication files except itself. Each original archive retains its own internal manifest and original bytes. The newly added appendices, dictionary, and index explain those saved records; this publication update makes no inference calls and changes no experimental results.
