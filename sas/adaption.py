"""Minimal Adaption Responses API client.

Lessons carried over from the archived attempt (archive/ADAPTION_FIX.md):
  * send reasoning={"effort": "none"} and verify on every response that it was
    honoured (reasoning_tokens == 0); otherwise outputs can burn the whole
    token allowance before returning a choice
  * one global rate gate shared by all threads; on HTTP 429 pause everything
    for >= 60 s (or Retry-After) and halve the rate
  * never retry because of bad model output here (that is the coordinator's job)
  * the key lives only in memory and is redacted from any stored error text

Transient failures (HTTP 5xx, notably the gateway 504s seen after ~60 s,
timeouts and connection errors) are retried with exponential backoff and
jitter. If they persist, TransientAPIError is raised; the runner keeps every
completed round and the run resumes from there on the next invocation.
A failed attempt may still have been billed, so each one is charged to the
ledger at its estimated input cost, marked uncertain, and counts toward the cap.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

API_BASE = "https://api.prod.adaptionlabs.ai/api/v1"

# Credits per million tokens (input, output), from the hosted catalogue as
# recorded by the archived client on 2026-11-07. Re-check before large runs.
PRICES = {
    "qwen3.5-397b": (0.55, 3.50),
    "glm-5.2": (1.40, 4.40),
    "deepseek-v4-flash": (0.04444, 0.13332),
    "gemma-4-31b-it": (0.09, 0.34),
}


class AdaptionError(RuntimeError):
    pass


class TransientAPIError(AdaptionError):
    """Retries exhausted on 5xx / timeout / connection errors. Safe to resume."""


class KeysExhausted(AdaptionError):
    """Every API key is retired (balance below threshold, 402 or 401). Resumable."""


class ReasoningControlError(AdaptionError):
    """The response did not confirm reasoning was disabled."""


class BudgetExceeded(AdaptionError):
    pass


def load_key() -> str:
    key = os.environ.get("ADAPTION_API_KEY", "").strip()
    env = Path(__file__).resolve().parent.parent / ".env"
    if not key and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("ADAPTION_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise AdaptionError("ADAPTION_API_KEY not set (environment or .env)")
    return key


def ledger_total(path: Path | None) -> float:
    if not path or not Path(path).exists():
        return 0.0
    total = 0.0
    for line in Path(path).read_text().splitlines():
        try:
            total += float(json.loads(line)["credits"])
        except (ValueError, KeyError, TypeError):
            continue   # a line torn by a kill mid-write; the entry is lost, not the ledger
    return total


def extract_text(data: dict) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts = []
    for item in data.get("output", []) or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for part in item.get("content", []) or []:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    parts.append(part.get("text", ""))
    return "".join(parts)


@dataclass
class RateGate:
    rps: float = 4.0
    max_inflight: int = 4
    min_rps: float = 1.0
    pause_s: float = 60.0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _next: float = 0.0
    _paused_until: float = 0.0
    _sem: threading.Semaphore | None = None
    cycles: int = 0

    def __post_init__(self):
        self._sem = threading.Semaphore(self.max_inflight)

    def acquire(self):
        self._sem.acquire()
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next, self._paused_until)
            self._next = start + 1.0 / self.rps
        time.sleep(max(0.0, start - time.monotonic()))

    def release(self):
        self._sem.release()

    def rate_limited(self, retry_after: float | None):
        with self._lock:
            now = time.monotonic()
            if self._paused_until > now:   # already handling this cycle
                return
            self.cycles += 1
            self._paused_until = now + max(self.pause_s, retry_after or 0.0)
            self.rps = max(self.min_rps, self.rps / 2)


class AdaptionClient:
    def __init__(self, *, key: str | None = None, gate: RateGate | None = None,
                 timeout: float = 120.0, max_credits: float = 20.0,
                 require_no_reasoning: bool = True, ledger_path: Path | None = None,
                 transport: httpx.BaseTransport | None = None, max_retries: int = 5,
                 backoff_base_s: float = 5.0, backoff_max_s: float = 120.0,
                 sleep=time.sleep):
        self._key = key or load_key()
        self.gate = gate or RateGate()
        self.max_credits = max_credits
        self.require_no_reasoning = require_no_reasoning
        self.ledger_path = ledger_path
        # The cap is cumulative per ledger (i.e. per experiment), not per invocation.
        self.spent = ledger_total(ledger_path) if ledger_path else 0.0
        self.max_retries, self.backoff_base_s, self.backoff_max_s = max_retries, backoff_base_s, backoff_max_s
        self._sleep = sleep
        self.transient_failures = 0          # attempts that failed transiently, this invocation
        self._lock = threading.Lock()
        self._http = httpx.Client(base_url=API_BASE, timeout=timeout, transport=transport,
                                  follow_redirects=False,
                                  headers={"Authorization": f"Bearer {self._key}",
                                           "Content-Type": "application/json"})

    def _redact(self, s: str) -> str:
        return s.replace(self._key, "[REDACTED]") if self._key else s

    @staticmethod
    def cost(model: str, n_in: int, n_out: int) -> float:
        pin, pout = PRICES.get(model, (2.0, 8.0))   # unknown model: price conservatively
        return (n_in * pin + n_out * pout) / 1e6

    def _post(self, payload: dict) -> httpx.Response:
        self.gate.acquire()
        try:
            return self._http.post("/responses", content=json.dumps(payload))
        finally:
            self.gate.release()

    def _log(self, entry: dict, credits: float):
        with self._lock:
            self.spent += credits
            if self.ledger_path:
                with open(self.ledger_path, "a") as f:
                    f.write(json.dumps({"t": time.time(), **entry, "credits": credits}) + "\n")

    def _backoff(self, retry: int) -> float:
        base = min(self.backoff_max_s, self.backoff_base_s * 2 ** retry)
        return base * random.uniform(0.5, 1.0)

    def respond(self, *, model: str, instructions: str, input: str,
                max_output_tokens: int = 512, temperature: float | None = None,
                on_attempt=None) -> dict:
        """Return {"text", "usage", "latency_s", "credits", "attempts", "served_model"}.

        on_attempt(record) is called once per HTTP attempt (including failed
        ones and retries) with the full request payload, the full raw response
        (JSON, or the redacted body / error), status, usage, latency, attempt
        number and served model (CLAUDE.md invariant 6). The key never appears
        in the payload, and headers are not logged."""
        if model.startswith("stack:"):
            raise AdaptionError("stacks are banned (CLAUDE.md invariant 4); use a hosted model ID")
        with self._lock:
            if self.spent >= self.max_credits:
                raise BudgetExceeded(f"spent {self.spent:.4f} >= cap {self.max_credits}")
        # store / agentic_memory / background: no server-side state (invariant 4).
        payload = {"model": model, "instructions": instructions, "input": input,
                   "max_output_tokens": max_output_tokens, "reasoning": {"effort": "none"},
                   "store": False, "agentic_memory": False, "background": False}
        if temperature is not None:
            payload["temperature"] = temperature
        # Conservative charge for an attempt whose billing is unknown: input only.
        est_in = int(len(instructions) + len(input)) // 3
        uncertain = self.cost(model, est_in, 0)

        errors = []
        retries = 0
        attempt = 0
        while True:
            attempt += 1
            t0 = time.monotonic()
            try:
                resp = self._post(payload)
                status = resp.status_code
            except httpx.TransportError as e:   # includes timeouts and dropped connections
                resp, status = None, type(e).__name__
            latency = time.monotonic() - t0
            if on_attempt is not None:
                on_attempt(self._attempt_record(payload, resp, status, latency, attempt))

            if status == 200:
                return self._accept(model, resp.json(), latency, attempt)
            if status == 429:
                ra = resp.headers.get("retry-after")
                self.gate.rate_limited(float(ra) if ra and ra.isdigit() else None)
                if self.gate.cycles >= 3:
                    raise AdaptionError("three rate-limit cycles; stopping")
                errors.append("429")
                continue                         # the gate enforces the pause
            if isinstance(status, int) and status < 500:
                raise AdaptionError(f"HTTP {status}: {self._redact(resp.text[:500])}")

            # 5xx or transport error: possibly billed, retry with backoff.
            self._log({"model": model, "status": status, "uncertain": True,
                       "latency_s": round(latency, 1)}, uncertain)
            with self._lock:
                self.transient_failures += 1
            errors.append(str(status))
            if retries >= self.max_retries:
                raise TransientAPIError(f"{len(errors)} failed attempts ({', '.join(errors)})")
            self._sleep(self._backoff(retries))
            retries += 1

    def _attempt_record(self, payload, resp, status, latency, attempt) -> dict:
        if resp is None:
            raw = {"transport_error": str(status)}
        else:
            try:
                raw = resp.json()
            except ValueError:
                raw = {"body": self._redact(resp.text[:20000])}
        usage = raw.get("usage") if isinstance(raw, dict) else None
        return {"t": time.time(), "attempt": attempt, "status": status,
                "latency_s": round(latency, 3), "request": payload, "response": raw,
                "usage": usage, "served_model": raw.get("model") if isinstance(raw, dict) else None}

    def _accept(self, model: str, data: dict, latency: float, attempt: int) -> dict:
        usage = data.get("usage") or {}
        n_in, n_out = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        r_tok = (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
        effort = (data.get("reasoning") or {}).get("effort")
        credits = self.cost(model, n_in, n_out)
        self._log({"model": model, "in": n_in, "out": n_out, "status": 200}, credits)
        if self.require_no_reasoning and (r_tok != 0 or effort not in ("none", None)):
            raise ReasoningControlError(
                f"reasoning not disabled: effort={effort!r} reasoning_tokens={r_tok!r}")
        if data.get("model") and not str(data["model"]).startswith(model):
            raise AdaptionError(f"model mismatch: asked {model}, got {data['model']}")
        return {"text": extract_text(data), "usage": {"input": n_in, "output": n_out,
                "reasoning": r_tok}, "latency_s": round(latency, 3),
                "credits": credits, "attempts": attempt, "status": data.get("status"),
                "served_model": data.get("model")}
