"""OpenRouter chat-completions client with a pool of API keys (Addendum 2).

Same interface as AdaptionClient.respond, so the coordinator, run store,
resume, stage enforcement and raw attempt logging are unchanged.

Per request (docs read 2026-11-08):
  POST https://openrouter.ai/api/v1/chat/completions
  provider = {"order": [<one slug>], "allow_fallbacks": false, "require_parameters": true}
  reasoning = per-model setting from configs/routes_openrouter.yaml ({"effort": "none"}
              or {"enabled": false}); the response must show no reasoning
  usage (incl. usage.cost in credits = USD) is always returned and goes to the ledger

Key pool:
  * keys from OPENROUTER_API_KEYS (env or .env), aliases k1, k2, ...; a key
    never appears in logs, records or errors, only its alias
  * each call takes the live key with the most remaining balance (thread-safe)
  * balances refresh at startup and every `refresh_every` calls from
    GET /api/v1/key (data.limit_remaining) or, if the key has no limit,
    GET /api/v1/credits (data.total_credits - data.total_usage); between
    refreshes spend is tracked locally from usage.cost
  * a key retires below `min_balance_usd`; on HTTP 402 (insufficient credit)
    or 401 it retires at once and the *same* call moves to the next key
    without counting as a failed attempt; all keys retired -> KeysExhausted
  * the key is not part of any fingerprint or manifest field
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from pathlib import Path

import httpx

from .adaption import (AdaptionError, BudgetExceeded, KeysExhausted, RateGate,
                       ReasoningControlError, TransientAPIError, ledger_total)

API_BASE = "https://openrouter.ai/api/v1"
ROOT = Path(__file__).resolve().parent.parent


def load_keys() -> list[str]:
    raw = os.environ.get("OPENROUTER_API_KEYS", "").strip()
    env = ROOT / ".env"
    if not raw and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("OPENROUTER_API_KEYS="):
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
    # Tolerate each key quoted individually ("k1","k2") as well as the whole value.
    keys = [k.strip().strip('"').strip("'").strip() for k in raw.split(",")]
    keys = [k for k in keys if k]
    if not keys:
        raise AdaptionError("OPENROUTER_API_KEYS not set (environment or .env)")
    return keys


class KeyPool:
    def __init__(self, keys: list[str], *, min_balance_usd: float = 2.0, refresh_every: int = 50,
                 transport: httpx.BaseTransport | None = None, timeout: float = 30.0):
        if not keys:
            raise AdaptionError("empty key pool")
        self._keys = {f"k{i + 1}": k for i, k in enumerate(keys)}
        self.aliases = list(self._keys)
        self.min_balance = min_balance_usd
        self.refresh_every = refresh_every
        self.remaining: dict[str, float | None] = {a: None for a in self.aliases}   # live balance
        self.spent_local: dict[str, float] = {a: 0.0 for a in self.aliases}         # since refresh
        self.retired: dict[str, str] = {}                                           # alias -> reason
        # In-flight reservations: each request holds its key's average call cost
        # until its response arrives, so concurrent selections spread across keys.
        self.inflight: dict[str, int] = {a: 0 for a in self.aliases}
        self._cost_sum, self._cost_n = 0.0, 0
        self.calls = 0
        self._lock = threading.Lock()
        self._http = httpx.Client(base_url=API_BASE, timeout=timeout, transport=transport,
                                  follow_redirects=False)

    # -- secrets ------------------------------------------------------------
    def redact(self, text: str) -> str:
        for alias, key in self._keys.items():
            text = text.replace(key, f"[{alias}]")
        return text

    def key(self, alias: str) -> str:
        return self._keys[alias]

    # -- balances -----------------------------------------------------------
    def _fetch_balance(self, alias: str) -> float | None:
        hdr = {"Authorization": f"Bearer {self._keys[alias]}"}
        try:
            r = self._http.get("/key", headers=hdr)
            if r.status_code in (401, 402):
                self.retired[alias] = f"key info HTTP {r.status_code}"
                return None
            if r.status_code == 200:
                lim = (r.json().get("data") or {}).get("limit_remaining")
                if lim is not None:
                    return float(lim)
            r = self._http.get("/credits", headers=hdr)
            if r.status_code == 200:
                d = r.json().get("data") or {}
                if d.get("total_credits") is not None:
                    return float(d["total_credits"]) - float(d.get("total_usage") or 0)
        except (httpx.HTTPError, ValueError):
            pass
        return None   # unknown: usable until a 402 says otherwise

    def refresh(self) -> dict:
        for alias in self.aliases:
            if alias in self.retired:
                continue
            bal = self._fetch_balance(alias)
            with self._lock:
                self.remaining[alias] = bal
                self.spent_local[alias] = 0.0
                if bal is not None and bal < self.min_balance:
                    self.retired.setdefault(alias, f"balance ${bal:.2f} < ${self.min_balance:.2f}")
        return self.status()

    def status(self) -> dict:
        with self._lock:
            return {a: {"remaining": self.effective(a), "retired": self.retired.get(a)} for a in self.aliases}

    def avg_cost(self) -> float:
        return self._cost_sum / self._cost_n if self._cost_n else 0.01

    def effective(self, alias: str) -> float:
        """Remaining balance minus local spend since refresh (no reservations)."""
        rem = self.remaining[alias]
        return float("inf") if rem is None else rem - self.spent_local[alias]

    def _score(self, alias: str) -> float:
        rem = self.remaining[alias]
        reserved = self.inflight[alias] * self.avg_cost()
        if rem is None:   # unknown balance: rank by least spent, then fewest in flight
            return 1e9 - self.spent_local[alias] - reserved
        return rem - self.spent_local[alias] - reserved

    # -- selection ----------------------------------------------------------
    def acquire(self, prefer: str | None = None) -> str:
        """Alias of the live key with the most remaining balance."""
        do_refresh = False
        with self._lock:
            self.calls += 1
            do_refresh = self.calls % self.refresh_every == 0
        if do_refresh:
            self.refresh()
        with self._lock:
            live = [a for a in self.aliases if a not in self.retired]
            if not live:
                raise KeysExhausted("all OpenRouter keys retired: "
                                    + "; ".join(f"{a}: {r}" for a, r in self.retired.items()))
            alias = prefer if prefer in live else max(live, key=lambda a: (self._score(a), -self.aliases.index(a)))
            self.inflight[alias] += 1
            return alias

    def release(self, alias: str) -> None:
        """The request on `alias` has returned (any outcome)."""
        with self._lock:
            self.inflight[alias] = max(0, self.inflight[alias] - 1)

    def record(self, alias: str, cost: float) -> None:
        with self._lock:
            self.spent_local[alias] += cost
            self._cost_sum += cost
            self._cost_n += 1
            if self.remaining[alias] is not None and self.effective(alias) < self.min_balance:
                self.retired.setdefault(alias, f"balance below ${self.min_balance:.2f}")

    def retire(self, alias: str, reason: str) -> None:
        with self._lock:
            self.retired.setdefault(alias, reason)


def _norm(s: str | None) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


class OpenRouterClient:
    def __init__(self, *, routes: dict, pool: KeyPool, max_usd: float, global_max_usd: float,
                 ledger_path: Path | None, global_ledger_path: Path | None,
                 require_no_reasoning: bool = True, rps: float = 8.0, max_inflight: int = 8,
                 timeout: float = 120.0, max_retries: int = 5, backoff_base_s: float = 5.0,
                 backoff_max_s: float = 120.0, transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep):
        self.routes, self.pool = routes, pool
        self.max_credits, self.global_max = max_usd, global_max_usd
        self.ledger_path, self.global_ledger = ledger_path, global_ledger_path
        self.require_no_reasoning = require_no_reasoning
        self.gates = {m: RateGate(rps=rps, max_inflight=max_inflight) for m in routes}
        self.max_retries, self.backoff_base_s, self.backoff_max_s = max_retries, backoff_base_s, backoff_max_s
        self._sleep = sleep
        self.spent = ledger_total(ledger_path) if ledger_path else 0.0
        self.global_spent = ledger_total(global_ledger_path) if global_ledger_path else 0.0
        self.transient_failures = 0
        self._lock = threading.Lock()
        self._http = httpx.Client(base_url=API_BASE, timeout=timeout, transport=transport,
                                  follow_redirects=False)

    @property
    def gate(self):   # the runner reads .gate.cycles for messages; report the worst model
        return max(self.gates.values(), key=lambda g: g.cycles)

    def _log(self, entry: dict, usd: float):
        line = json.dumps({"t": time.time(), **entry, "credits": usd, "usd": usd})
        with self._lock:
            self.spent += usd
            self.global_spent += usd
            for path in (self.ledger_path, self.global_ledger):
                if path:
                    with open(path, "a") as f:
                        f.write(line + "\n")

    def _check_budget(self):
        with self._lock:
            if self.global_spent >= self.global_max:
                raise BudgetExceeded(f"global ledger ${self.global_spent:.2f} >= hard stop ${self.global_max:.2f}")
            if self.spent >= self.max_credits:
                raise BudgetExceeded(f"experiment ledger ${self.spent:.2f} >= cap ${self.max_credits:.2f}")

    def payload(self, model: str, instructions: str, input: str, max_output_tokens: int,
                temperature: float | None) -> dict:
        r = self.routes[model]
        p = {"model": r["slug"],
             "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": input}],
             "max_tokens": max_output_tokens, "stream": False,
             "reasoning": r.get("reasoning", {"effort": "none"}),
             "provider": {"order": [r["provider"]], "allow_fallbacks": False, "require_parameters": True}}
        if temperature is not None:
            p["temperature"] = temperature
        return p

    def _record(self, payload, resp, status, latency, attempt, alias, raw=None) -> dict:
        if raw is None:
            if resp is None:
                raw = {"transport_error": str(status)}
            else:
                try:
                    raw = resp.json()
                except ValueError:
                    raw = {"body": self.pool.redact(resp.text[:20000])}
        raw = json.loads(self.pool.redact(json.dumps(raw))) if isinstance(raw, dict) else raw
        usage = raw.get("usage") if isinstance(raw, dict) else None
        return {"t": time.time(), "attempt": attempt, "status": status, "latency_s": round(latency, 3),
                "key_alias": alias, "request": payload, "response": raw, "usage": usage,
                "served_model": raw.get("model") if isinstance(raw, dict) else None,
                "provider": raw.get("provider") if isinstance(raw, dict) else None}

    def respond(self, *, model: str, instructions: str, input: str, max_output_tokens: int = 512,
                temperature: float | None = None, on_attempt=None, prefer_key: str | None = None) -> dict:
        if model not in self.routes:
            raise AdaptionError(f"no OpenRouter route for model {model!r}")
        route = self.routes[model]
        payload = self.payload(model, instructions, input, max_output_tokens, temperature)
        gate = self.gates[model]
        errors, retries, attempt = [], 0, 0
        while True:
            self._check_budget()
            alias = self.pool.acquire(prefer=prefer_key)
            attempt += 1
            t0 = time.monotonic()
            gate.acquire()
            try:
                resp = self._http.post("/chat/completions", content=json.dumps(payload), headers={
                    "Authorization": f"Bearer {self.pool.key(alias)}", "Content-Type": "application/json",
                    "X-OpenRouter-Title": "selection-against-safety"})
                status = resp.status_code
            except httpx.TransportError as e:
                resp, status = None, type(e).__name__
            finally:
                gate.release()
                self.pool.release(alias)
            latency = time.monotonic() - t0
            data = None
            if status == 200:
                try:
                    data = resp.json()
                except ValueError:
                    status = "bad_json"
            # Errors can arrive inside a 200 body (docs: check for `error` even on 200).
            if isinstance(data, dict) and data.get("error") and not data.get("choices"):
                code = (data["error"] or {}).get("code")
                status = code if isinstance(code, int) else "error_in_200"
            rec = self._record(payload, resp, status, latency, attempt, alias, raw=data)
            if on_attempt is not None:
                on_attempt(rec)
            body = rec["response"] if isinstance(rec["response"], dict) else {}
            err = (body.get("error") or {}) if isinstance(body, dict) else {}
            meta = err.get("metadata") or {}

            if status == 200:
                return self._accept(model, route, data, latency, attempt, alias)
            if status == 402 and meta.get("reason") == "in_flight_budget_exhausted":
                ra = resp.headers.get("retry-after") if resp is not None else None
                self._sleep(float(ra) if ra and ra.replace(".", "").isdigit() else 5.0)
                attempt -= 1                     # not a failed attempt: wait and resend
                continue
            if status in (401, 402):
                # Key-level failure: retire this key, resend the same call on the next one.
                self.pool.retire(alias, f"HTTP {status}: {self.pool.redact(str(err.get('message', '')))[:120]}")
                self._log({"model": model, "status": status, "key_alias": alias, "retired": True}, 0.0)
                attempt -= 1
                continue
            if status == 429:
                ra = resp.headers.get("retry-after") if resp is not None else None
                gate.rate_limited(float(ra) if ra and ra.isdigit() else None)
                if gate.cycles >= 3:
                    raise AdaptionError(f"three rate-limit cycles on {model}; stopping")
                errors.append("429")
                continue
            if isinstance(status, int) and 400 <= status < 500 and status != 408:
                raise AdaptionError(f"HTTP {status}: {self.pool.redact(json.dumps(err) or '')[:400]}")
            # 5xx, 408, timeouts, transport and empty/bad bodies: OpenRouter does not
            # bill failed generations; logged at $0 with the status for accounting.
            self._log({"model": model, "status": status, "key_alias": alias, "uncertain": True,
                       "latency_s": round(latency, 1)}, 0.0)
            with self._lock:
                self.transient_failures += 1
            errors.append(str(status))
            if retries >= self.max_retries:
                raise TransientAPIError(f"{len(errors)} failed attempts ({', '.join(errors)})")
            self._sleep(min(self.backoff_max_s, self.backoff_base_s * 2 ** retries) * random.uniform(0.5, 1.0))
            retries += 1

    def _accept(self, model, route, data, latency, attempt, alias) -> dict:
        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or ""
        r_tok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        r_text = msg.get("reasoning") or ""
        cost = float(usage.get("cost") or 0.0)
        provider = data.get("provider")
        self._log({"model": model, "slug": route["slug"], "provider": provider, "key_alias": alias,
                   "in": usage.get("prompt_tokens"), "out": usage.get("completion_tokens"),
                   "reasoning": r_tok, "status": 200}, cost)
        self.pool.record(alias, cost)
        if self.require_no_reasoning and ((r_tok or 0) != 0 or r_text.strip()):
            raise ReasoningControlError(f"{model} on {route['provider']}: reasoning not disabled "
                                        f"(reasoning_tokens={r_tok!r}, reasoning text {len(r_text)} chars)")
        pinned = _norm(route["provider"].split("/")[0])
        if provider and pinned not in _norm(provider) and _norm(provider) not in pinned:
            raise AdaptionError(f"{model}: served by {provider!r}, pinned {route['provider']!r}")
        served = data.get("model")
        if served and not str(served).startswith(route["slug"].split(":")[0]):
            raise AdaptionError(f"model mismatch: asked {route['slug']}, got {served}")
        return {"text": text, "usage": {"input": int(usage.get("prompt_tokens") or 0),
                                        "output": int(usage.get("completion_tokens") or 0), "reasoning": r_tok},
                "latency_s": round(latency, 3), "credits": cost, "attempts": attempt,
                "status": choice.get("finish_reason"), "served_model": served, "provider": provider,
                "key_alias": alias, "reasoning_field_present": r_tok is not None}
