The repository root contains the full report, main result tables, chart, and key validation records.

The complete folder tree described below is inside [full-results.zip](full-results.zip). Extract it into a new folder before running the verification commands. The ZIP contains all 172 package files. Its inner manifest lists all other package files. The outer [FILE_MANIFEST.json](FILE_MANIFEST.json) identifies the files uploaded to this repository.

This repository contains the complete results of the paced Adaption study of worker selection after a correct objection.

The main study finished on 7 November 2026. It has 160 complete runs and 3,840 valid main assignments. Each model has 40 paired task seeds. Eight probes and 192 pilot calls are separate from the main sample. The new run has 4,040 successful calls in total.

The README reports the main findings and shows the chart. The `results/live_paced` folder contains the full report, all 160 main result records, the exact paired analysis, CSV tables, PNG and SVG charts, final status, and audit evidence. The root protocol, design note, API repair note, and AI review give the study context. The `paced_study` and `tests_paced` folders contain the exact source files used by the completed study. Their hashes remain unchanged.

**Original records**

The `archives` folder preserves the original bytes of 1,071 files. Its index lists every archive, part, member path, size, SHA-256 hash, and Git blob hash. The archives include:

- All 170 new run folders, with tasks, prompts, raw responses, linked event logs, checkpoints, and scores.
- New pacing records, the SQLite credit ledger, its saved side files, source snapshots, and study records.
- All 46 earlier run folders and all earlier study, amendment, source, audit, and cost records.
- The technical diagnostic journal and its requests and responses.
- Original protocol files, source-workspace reports, native tokenizer verification reports, and tokenizer asset manifests.

The earlier main batch is excluded in full from the scientific result. It ended with no complete main run. It remains here only for review and cost history. The probes and pilots are also excluded from the main effect estimate.

The archives use deterministic tar and gzip formats. Large archives are split into parts of at most 90,000 bytes. Join parts in the order stated in `archives/INDEX.json` before decompressing. No original record is changed by this split. The archive member hashes refer to the original bytes.

No API key, key receipt, private socket, model weight, tokenizer data asset, virtual environment, or bytecode cache is included. The native tokenizer asset manifests identify upstream revisions and source-file hashes. They are included for provenance. The tokenizer data assets are not needed to reproduce the saved analysis. The unrun follow-up plan is outside this publication.

**Local checks**

Use Python 3.13 to match the study's analysis runtime. The following command uses only the Python standard library and the saved analysis code. It disables network connections. It does not make model calls or write files.

```sh
python3 reproduce_analysis.py
```

The script checks every listed publication file, every joined archive, every original archived member, and all 24 frozen source hashes. It then repeats the full main analysis from `results.json`. The result must match `analysis.json` exactly. It checks 40 complete pairs per model. This is a publication-integrity and analysis check. It is not a new model experiment, a human review, or a provider billing check.

`MANIFEST.json` lists all publication files except itself. A file cannot contain its own stable content hash. The Git commit and tree identify the manifest's exact bytes. The manifest contains SHA-256, Git blob SHA-1, size, and type for each listed file.

To restore all original records, use a new folder outside the repository:

```sh
python3 restore_records.py ../apartswarms-original-records
```

The restoration script checks archive hashes and member paths before writing. It does not alter the repository or contact a service. The restored files retain their original relative paths below the original study package root.

**Audit and path limits**

The original `audit.json` is a record of the full audit performed in the source workspace. It checked source files, scores, the paired analysis, event-log chains, credit carry, and pacing. That audit passed with zero issues. Its `paid_calls: 0` field means that the audit itself made no paid calls. It does not mean that the experiment was offline.

Some original provenance records contain absolute paths from the source computer. These paths are historical metadata. They are not public download links. The original full audit uses an absolute prior-study path from the preserved carry receipt. It will not run unchanged on every other computer. Do not edit that receipt to make the old audit pass: that would change its hash and the original provenance chain. The portable `reproduce_analysis.py` has a separate and narrower scope.

The chart source is `build_result_files.py`. Its inputs are listed in `result_files_provenance.json`. To draw the chart again, install Matplotlib in a separate local environment and run the script against the saved result folder. This changes only derived chart and table files; it does not make inference calls. The committed PNG and SVG are the original rendered files.

**Cost and interpretation**

The total estimated charge is 9.15338335 Adaption credits. Another 9.611280 credits remains reserved for unknown charges from earlier attempts. The total committed amount is 18.76466335 credits, below the 100-credit limit. These are local estimates and reserves. Provider billing is not verified. The experiment made no OpenRouter calls.

Neither model showed clear evidence of a penalty from the worker-credit cue. Both primary intervals include zero. This does not prove that selection against safety is absent. The test used fixed local workers, one live coordinator, explicit rules, immediate audits, and reasoning effort set to `none`. It did not test live worker adaptation or the formation of team roles. The model weights and deployment revision were not independently verified.

The tests, audits, and independent reviews were automated or performed by AI. No human scientific review is claimed.
