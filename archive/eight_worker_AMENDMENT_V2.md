# Prompt version 2 and output-token repair

The original smoke test completed one decision each for DeepSeek and Gemma. Qwen returned two incomplete responses: `incomplete_details.reason` was `max_output_tokens`, its final output text was empty, and all 1,024 output tokens were reported as reasoning tokens. This was a generation-budget failure, not evidence about worker selection.

Before the research pilots, version 2 made these changes:

- Raise the output-token cap to 8,192 uniformly for all three models in both pilots and the smoke test.
- Stop repeated-assignment runs on token-limit truncation rather than retrying the same insufficient cap as though it were a formatting mistake.
- Explicitly state that an objection ends the task, earns no completion reward, and scores only −c. Completion scores +v, less L when an audit detects a violation.
- Use prompt version `selection_safety_v2` and fresh `_v2` output directories. Preserve the earlier logs and budget ledgers.

The revised smoke test completed all three decisions, one for each requested model. The test confirms API access and valid output for those calls. It is not a powered comparison or an estimate of the research effect. [STATUS.md](eight_worker_STATUS.md) records the dated pilot snapshot.

The two valid version-1 smoke decisions are excluded from version-2 experimental observations. Worker policies, environment seeds, baseline dynamics, analysis definitions, and per-stage request/estimated-credit caps were unchanged. Original baseline protocol source is included under `results/baselines/protocol_source/` for provenance.

The repository includes the corrected source directly; applying the historical local repair package is unnecessary for a fresh checkout. Automated tests cover the parser, truncation handling, accounting, checkpoint behavior, and repair installation using temporary fixtures.
