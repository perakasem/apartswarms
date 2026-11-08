# Check the saved prompt comparison

The archive contains the exact prompts, raw responses, worker facts, scores, source files, and cost records. It also contains the earlier cost records. The earlier study results are not part of the new sample.

## Check the records without model calls

1. Extract `prompt-full-results.zip` into a new folder.
2. Use Python 3.13, the tested version. Install `scipy==1.18.1` before the check.
3. From that folder, run `python3 -B reproduce_prompt.py`.

The check blocks network access. It writes no files and makes no model calls. It checks the archive manifest, frozen source hashes, saved messages, response parsing, worker outcomes, scores, statistical analysis, cost carry, and cost limits. A passing result has `"passed": true` and an empty `issues` list.

The check uses the frozen code in `results/live_prompt/source`. The separate numeric reviewer does not import the study scorer. Its source and test receipt are also included.

A hash manifest checks file consistency. It does not prove the source of an untrusted archive. These checks do not verify provider account deductions or the exact hosted model revision.

## Repeat the tokenizer checks

The archive contains the native-tokenizer check receipt and both asset manifests. The large tokenizer assets are not included. No model weights are needed.

The checked assets came from these exact revisions:

- Qwen: `Qwen/Qwen3.5-397B-A17B`, revision `8472618112abcbd45acbcdc58436aff4233c23f7`.
- GLM: `zai-org/GLM-5.2`, revision `cf457fa734ab149ffef225f80893eb38c6ff5cdc`.

Use a separate work folder to repeat these checks. Copy the frozen source tree into it. Install the packages in `prompt_requirements.txt`. Put the listed assets and the matching manifest in `tokenizers/qwen` and `tokenizers/glm`. Each asset must match the SHA256 in its manifest.

Run `python3 -m prompt_study.cli verify` for the offline tests. Then run `python3 -m prompt_study.tokenization` for the full native context check. The native check blocks network access. It does not call a model. The archived check covered ten history policies and 41,280 contexts per model.

The archive verifier checks the saved tokenizer receipt. It does not load these omitted assets or repeat tokenization. Each actual study request was also counted before dispatch.

## Repeat the charts

With the pinned packages installed, use a separate work copy. Run `python3 build_prompt_result_files.py results/live_prompt`. This reads completed results and a passed audit. It makes no model calls. Keep the original archive unchanged for later integrity checks.

Do not rerun the completed live study. The saved authorization covers one collection. A new paid collection needs a new plan and cost allowance.
