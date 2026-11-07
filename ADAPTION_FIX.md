The Adaption runner uses two changes: an explicit reasoning control and one shared request-rate gate.

The inference endpoint is `https://api.prod.adaptionlabs.ai/api/v1/responses`. The model IDs are `qwen3.5-397b` and `glm-5.2`.

Add this field at the top level of each request:

```json
"reasoning": {"effort": "none"}
```

The earlier calls without this field sometimes used the full output allowance before they returned a worker choice. Increasing the allowance from 2,000 to 4,000 tokens did not make all probes pass. Some requests also returned HTTP 504 after about 60 seconds. The client timeout was 120 seconds.

Two short diagnostic calls with the new field returned valid JSON. Each returned reasoning effort `none` and zero reasoning tokens. The later version 1.2 probes and full pilot also passed. All 500 successful version 1.2 calls used at most 13 output tokens. The paced replacement therefore uses a 512-token output limit.

Do not assume that a request field was honored. The transport checks these returned fields on every accepted response:

```text
reasoning.effort == "none"
usage.output_tokens_details.reasoning_tokens == 0
```

The reasoning-token count must be an integer. The model ID must match. Input, output, and total token counts must be valid and consistent. A failed control check stops new calls. Native tokenizer checks and a 256-token allowance bound the input. The complete input limit remains 6,000 tokens.

The requested reasoning field was confirmed by actual responses on these deployments. The public Adaption request schema checked for this task did not list it. Do not assume the same behavior on other models or later deployments. The saved responses are the evidence for these calls.

The earlier version 1.2 main run then hit HTTP 429. It used at most 16 concurrent calls with no shared dispatch spacing. There were 500 successful new calls before the first rate-limit failure. This observed count does not establish the provider's published quota. The old retry loop then recorded 418 HTTP 429 attempts. That run stopped with no complete main run.

The paced replacement uses these fixed controls:

- One gate covers both models and all retries.
- Start at four requests per second, with no stored burst allowance.
- Permit at most four active requests and eight active episodes.
- On HTTP 429, pause all new requests for at least 60 seconds. Honor a longer `Retry-After` value.
- Reduce the rate to two, then one request per second after separate rate-limit cycles.
- Count concurrent failures from one request group as one cycle.
- Stop on the third cycle. Do not increase the rate during the study.
- Permit at most one transport retry per turn. Do not retry invalid model output.

The HTTP transport captures a bounded, redacted error body and allowed rate-limit headers. It parses `Retry-After` as seconds or an HTTP date. These records support later diagnosis without exposing the key.

The old batch remains in `results/live`. Its full main batch is excluded from the new scientific sample. Its 940 attempts remain in the budget history. The new `results/live_paced` ledger carries 10.55734950 committed credits. This includes 9.611280 credits reserved for unknown charges. HTTP errors are not assumed to be free.

All 109 offline tests passed with network access blocked. The full local simulation passed 4,040 calls. Its independent audit passed. The native checks covered 12,384 complete contexts across both models. These checks occurred before the paced live run.

The key stays in process memory. A private local socket supplies it from the hidden Terminal prompt. No key is passed in a shell argument or saved in the experiment records.

Read `results/live_paced/status.json`, `REPORT.md`, and `audit.json` for the final live result. This note explains the repair. It does not replace the study result or a provider billing receipt.
