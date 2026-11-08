"""Run LLM coordinators over an experiment grid.

Resumable at three levels, so HTTP 504s, crashes or Ctrl-C never lose paid work:
  * per call: 5xx/timeouts are retried with exponential backoff, and a 429
    resends only that call after a short jittered wait (sas/openrouter.py)
  * per round: every completed round is fsynced to the run's .partial file, and
    a rerun continues from the first missing round (sas/grid.py)
  * per grid: completed runs are skipped; just rerun the same command
A run that still fails transiently is re-queued once in the same invocation.
Failures are contained per model: three transient run failures in a row on one
model (its provider is likely down), sustained rate limiting, or a systemic
error stop that model only; its in-flight runs pause after their current round
and the other models continue. Budget caps, an empty key pool and Ctrl-C stop
every model. Exit codes: 0 all complete, 2 incomplete but resumable (including
budget caps and rate limiting), 1 a systemic error to fix first (reasoning
control, HTTP 4xx, provider/model mismatch, replay mismatch).

Job order is seed-major (all cells and models for seed s before seed s+1),
so a stop at any point leaves a balanced design (per model, if one stops early).

  uv run scripts/run_experiment.py --config configs/confirmatory.yaml --dry-run
  uv run scripts/run_experiment.py --config configs/confirmatory.yaml
  uv run scripts/run_experiment.py --config configs/full_grid.yaml --model glm-5.2 --cells rho0_
Use model name "fake" for an offline run through the full LLM code path, and
"fake-flaky" to rehearse a 504 outage (fails after 25 calls, recovers after 3).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.api import (APIError, BudgetExceeded, KeysExhausted, RateLimited,  # noqa: E402
                     TransientAPIError, ledger_total)
from sas.coordinators import (BrokeFakeClient, FakeClient, FlakyFakeClient, LLMCoordinator,  # noqa: E402
                              RateLimitedFakeClient, Uniform)
from sas.env import Observation, ReplayMismatch, run_episode  # noqa: E402
from sas.grid import (RESULTS, StopRequested, execute_run, load_experiment,  # noqa: E402
                      partial_progress, resolve_run, run_path)
from sas.prompts import NOTES_MAX_CHARS, prompt_hash, round_prompt, system_prompt  # noqa: E402
from sas.tapes import make_tapes  # noqa: E402

CHARS_PER_TOKEN = 3.5          # conservative for label/number-heavy text
REPLY_OVERHEAD_TOKENS = 30     # JSON wrapper + worker label
PROBES = RESULTS / "probes"
BREAKER_CONSECUTIVE = 3        # transient run failures in a row before stopping
REQUEUES = 1                   # extra attempts per run within one invocation


def parse_deadline(hhmm: str) -> float:
    """Today's local HH:MM as a timestamp; refuses a time already past."""
    import datetime as dt
    h, m = (int(x) for x in hhmm.split(":"))
    now = dt.datetime.now()
    when = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if when <= now:
        sys.exit(f"--deadline {hhmm} is already past (now {now:%H:%M})")
    return when.timestamp()


def prompts_approved(stage: str) -> tuple[bool, str]:
    """Change 10: live runs need the current prompts' approval hash to equal the
    approved one (APPROVED_PROMPT_HASH or PREREGISTRATION §0). Smoke is exempt."""
    from sas import prompt_approval as pa
    if stage == "smoke":
        return True, "smoke stage: prompt approval not required"
    cur, ok = pa.approval_hash(), pa.approved_hash()
    if ok is None:
        return False, (f"no approved prompt hash; review docs/PROMPTS_RENDERED.md (hash {cur}) and record it "
                       "in APPROVED_PROMPT_HASH or the PREREGISTRATION §0 'Prompt hash' row")
    if ok != cur:
        return False, (f"prompts changed since approval (approved {ok}, current {cur}); re-render with "
                       "scripts/render_prompts.py and re-approve")
    return True, f"prompts approved ({cur})"


def probe_file(api: str, model: str) -> Path:
    return PROBES / f"{api}-{model}.json"


def probe_passed(model: str, api: str = "openrouter") -> bool:
    path = probe_file(api, model)
    return path.exists() and json.loads(path.read_text()).get("passed") is True


def probe_calibration(model: str, api: str = "openrouter") -> dict | None:
    """Real token use from the probe: characters per input token, and mean
    output tokens per call (which also sizes the notes echoed back as input)."""
    path = probe_file(api, model)
    if not path.exists():
        return None
    res = [r for r in json.loads(path.read_text()).get("results", []) if r.get("ok") and r.get("usage")]
    chars = sum(r["prompt_chars"] + r.get("system_chars", 0) for r in res)
    tin = sum(r["usage"]["input"] for r in res)
    if not res or not tin:
        return None
    return {"chars_per_token": chars / tin,
            "out_per_call": sum(r["usage"]["output"] for r in res) / len(res), "n_calls": len(res)}


def estimate_tokens(exp, cell, calib: dict | None = None) -> tuple[int, int]:
    """Token use of one LLM run, from every real prompt of a uniform run.
    calib=None: upper bound (notes at the full NOTES_MAX_CHARS every round,
    echoed back as input and written as output; CHARS_PER_TOKEN).
    calib from the probe: observed chars/token and output tokens per call
    (notes echoed as input ~ the previous reply). No re-asks or retries."""
    sizes = []

    class Recorder(Uniform):
        def choose(self, obs: Observation):
            sizes.append(len(round_prompt(obs, cell.framing)) + len(system_prompt(cell, exp.T)))
            return super().choose(obs)

    run_episode(cell, make_tapes(0, exp.T), Recorder(), exp.T)
    if calib:
        out = calib["out_per_call"]
        tin = sum(sizes) / calib["chars_per_token"] + out * (exp.T - 1)
        return int(tin), int(out * exp.T)
    notes_tokens = NOTES_MAX_CHARS / CHARS_PER_TOKEN
    tin = sum(sizes) / CHARS_PER_TOKEN + notes_tokens * (exp.T - 1)
    tout = (notes_tokens + REPLY_OVERHEAD_TOKENS) * exp.T
    return int(tin), int(tout)


def price_fn(exp, model: str):
    """(input tokens, output tokens) -> USD from the route's price table."""
    route = exp.routes()[model]
    return lambda n_in, n_out: (n_in * route["price_in"] + n_out * route["price_out"]) / 1e6


def project_cost(exp, jobs, resumable, models, cells) -> dict:
    """Per model: (upper-bound cost, probe-calibrated cost or None)."""
    out = {}
    api = exp.llm_settings()["api"]
    for m in models:
        mj = [j for j in jobs if j[0] == m]
        if not mj:
            continue
        cost = price_fn(exp, m)
        calib = probe_calibration(m, api)
        ub = {c.cell_id: estimate_tokens(exp, c) for c in cells}
        cal = {c.cell_id: estimate_tokens(exp, c, calib) for c in cells} if calib else None
        frac = [1 - resumable[j] / exp.T for j in mj]
        out[m] = {"runs": len(mj),
                  "upper": sum(f * cost(*ub[c.cell_id]) for f, (_, c, _) in zip(frac, mj)),
                  "calibrated": (sum(f * cost(*cal[c.cell_id]) for f, (_, c, _) in zip(frac, mj))
                                 if cal else None),
                  "calib": calib}
    return out


PILOT_EXPECTED = {"rho": {0.0, 1.0}, "c": {5.0}, "pi": {0.25}, "feedback": {"outcome"},
                  "visibility": {"blind"}, "framing": {"points"}, "tone": {"neutral"}}


def sanity_print(exp, cells, models, seed_of, llm, proj, spent) -> None:
    """Addendum §4a.5: everything a live run will do, before it does it."""
    print("=" * 72)
    print(f"LIVE RUN SANITY CHECK  stage = {exp.stage}   config = {exp.source}")
    seeds = sorted({s for v in seed_of.values() for s in v})
    print(f"  seeds: {len(seeds)} ({seeds[0]}-{seeds[-1]})" + (
        "" if len({len(v) for v in seed_of.values()}) == 1 else
        "  per cell: " + ", ".join(f"{k}={len(v)}" for k, v in seed_of.items())))
    print("  cells:")
    for c in cells:
        print(f"    {c.cell_id:42s} rho={c.rho:g} c={c.c:g} pi={c.pi:g} feedback={c.feedback} "
              f"{c.visibility} {c.framing} {c.tone}")
    if exp.stage == "pilot":
        got = {k: {getattr(c, k) for c in cells} for k in PILOT_EXPECTED}
        bad = {k: sorted(v) for k, v in got.items() if v != PILOT_EXPECTED[k]}
        print("  pilot design check: " + ("OK (rho in {0,1}, c=5, pi=0.25, outcome-only, blind, points)"
                                          if not bad else f"MISMATCH {bad}"))
    print(f"  API: {exp.llm_settings()['api']} ({exp.api_host()})")
    routes = exp.routes()
    print("  models: " + ", ".join(f"{m} -> {routes[m]['slug']} @ {routes[m]['provider']}" if m in routes else m
                                   for m in models))
    print(f"  T = {exp.T}, temperature = {llm['temperature']}, max_output_tokens = {llm['max_output_tokens']}, "
          f"max_reasks = {llm['max_reasks']}, reasoning off = {llm['require_no_reasoning']}")
    total_ub = sum(p["upper"] for p in proj.values())
    cal_known = all(p["calibrated"] is not None for p in proj.values())
    unit = "USD"
    for m, p in proj.items():
        cal = (f"~{p['calibrated']:.2f} {unit} (probe: {p['calib']['chars_per_token']:.2f} chars/token, "
               f"{p['calib']['out_per_call']:.0f} output tokens/call)" if p["calibrated"] is not None
               else "no probe calibration")
        print(f"    {m}: {p['runs']} runs; projected {cal}; upper bound {p['upper']:.2f}")
    total = sum(p["calibrated"] for p in proj.values()) if cal_known else None
    print(f"  projected spend: {('~%.2f' % total) if total is not None else 'n/a'} {unit} "
          f"(upper bound {total_ub:.2f}); ledger so far {spent:.2f}; cap {llm['max_credits']}")
    print(f"  global hard stop: ${llm['global_max_usd']:.2f} across all keys and experiments "
          f"(global ledger so far ${ledger_total(RESULTS / 'openrouter_ledger.jsonl'):.2f})")
    print("=" * 72)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--model", action="append", help="subset of config models (repeatable)")
    ap.add_argument("--cells", default="", help="substring filter on cell_id")
    ap.add_argument("--seeds", type=int, default=None, help="use only the first N seeds of each cell")
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-unprobed", action="store_true",
                    help="skip the requirement that scripts/probe_models.py passed for each model")
    ap.add_argument("--deadline", default=None, metavar="HH:MM",
                    help="local time: after it, start no new runs; in-flight runs finish; exit 2")
    ap.add_argument("--confirm", action="store_true",
                    help="start a live run after the sanity print (without it, the script prints and exits)")
    args = ap.parse_args()

    exp = load_experiment(args.config)
    llm = exp.llm_settings()
    deadline = parse_deadline(args.deadline) if args.deadline else None
    models = args.model or exp.models
    cells = [c for c in exp.cells() if args.cells in c.cell_id]
    seed_of = {c.cell_id: (exp.seeds_for(c)[: args.seeds] if args.seeds else exp.seeds_for(c))
               for c in cells}

    # Seed-major order: a stop at any point leaves every cell with ~equal seeds.
    all_jobs = sorted(((m, c, s) for m in models for c in cells for s in seed_of[c.cell_id]),
                      key=lambda j: (j[2], cells.index(j[1]), models.index(j[0])))
    jobs = [j for j in all_jobs if resolve_run(exp, *j) is None]
    resumable = {j: partial_progress(run_path(exp, *j)) for j in jobs}
    n_partial = sum(1 for v in resumable.values() if v)
    print(f"{exp.name} [{exp.stage}]: {len(models)} model(s) x {len(cells)} cell(s); "
          f"{len(all_jobs) - len(jobs)} complete, {len(jobs)} to run"
          + (f" ({n_partial} will resume from a checkpoint)" if n_partial else ""))

    if args.dry_run:
        unit = "USD"
        proj = project_cost(exp, jobs, resumable, models, cells)
        for m, p in proj.items():
            cal = f"~{p['calibrated']:.2f} (probe-calibrated)" if p["calibrated"] is not None else "no probe yet"
            print(f"  {m}: {p['runs']} runs, {cal}; upper bound {p['upper']:.2f} {unit}")
        spent = ledger_total(exp.out_dir() / "ledger.jsonl")
        print(f"upper bound total ~{sum(p['upper'] for p in proj.values()):.2f} {unit}; ledger so far "
              f"{spent:.2f}; cumulative cap {llm['max_credits']}. Upper bound assumes notes at the "
              f"{NOTES_MAX_CHARS}-char limit every round; neither figure includes retries or re-asks.")
        return
    if not jobs:
        return

    FAKES = {"fake", "fake-flaky", "fake-broke", "fake-ratelimited"}
    live = sorted({m for m, _, _ in jobs if m not in FAKES})
    if live and exp.disabled:
        sys.exit(f"refusing to start: config disabled ({exp.disabled})")
    if live:
        ok, msg = prompts_approved(exp.stage)
        print(msg)
        if not ok:
            sys.exit(f"refusing to start: {msg}")
    if live and not args.allow_unprobed:
        missing = [m for m in live if not probe_passed(m, llm["api"])]
        if missing:
            sys.exit(f"no passing probe for {missing}; run scripts/probe_models.py --model ... first")
    if live:
        proj = project_cost(exp, jobs, resumable, models, cells)
        sanity_print(exp, cells, models, seed_of, llm, proj,
                     ledger_total(exp.out_dir() / "ledger.jsonl"))
        if not args.confirm:
            print("not started. Review the above, then rerun with --confirm.")
            return
    exp.out_dir().mkdir(parents=True, exist_ok=True)
    client = None
    if live:
        from sas.openrouter import KeyPool, OpenRouterClient, load_keys
        pool = KeyPool(load_keys())
        print("key balances (alias: remaining USD): " + ", ".join(
            f"{a}: {'retired (' + v['retired'] + ')' if v['retired'] else ('unknown' if v['remaining'] == float('inf') else '$%.2f' % v['remaining'])}"
            for a, v in pool.refresh().items()))
        client = OpenRouterClient(routes=exp.routes(), pool=pool, max_usd=llm["max_credits"],
                                  global_max_usd=llm["global_max_usd"],
                                  ledger_path=exp.out_dir() / "ledger.jsonl",
                                  global_ledger_path=RESULTS / "openrouter_ledger.jsonl",
                                  require_no_reasoning=llm["require_no_reasoning"],
                                  rps=llm["rps"], max_inflight=llm["max_inflight"],
                                  inflight_by_model=llm["max_inflight_by_model"],
                                  inflight_floor=llm["inflight_floor"],
                                  max_retries=llm["max_retries"])
        print(f"ledger so far: ${client.spent:.4f} of cap ${llm['max_credits']}; "
              f"global ${client.global_spent:.4f} of ${llm['global_max_usd']}")
    fakes = {"fake": FakeClient(), "fake-flaky": FlakyFakeClient(), "fake-broke": BrokeFakeClient(),
             "fake-ratelimited": RateLimitedFakeClient()}
    # One stop event per model: a model-level failure (systemic error, sustained
    # 429, transient circuit breaker) pauses only that model's runs; budget caps,
    # an empty key pool and Ctrl-C stop every model.
    stops = {m: threading.Event() for m in {j[0] for j in jobs}}

    def stop_all():
        for ev in stops.values():
            ev.set()

    def one(job):
        m, cell, seed = job
        coord = LLMCoordinator(fakes.get(m, client), m,
                               max_output_tokens=llm["max_output_tokens"],
                               temperature=llm["temperature"], max_reasks=llm["max_reasks"])
        route = exp.routes().get(m, {})
        extra = {"kind": "llm", "model": m, "prompt_hash": prompt_hash(cell, exp.T),
                 "api": llm["api"], "api_host": exp.api_host(),
                 "route": {k: route[k] for k in ("slug", "provider", "reasoning") if k in route},
                 "llm_settings": {k: llm[k] for k in
                                  ("max_output_tokens", "temperature", "max_reasks", "require_no_reasoning")}}
        return execute_run(exp, cell, seed, coord, m, extra, stop=stops[m])

    tag = lambda j: f"{j[0]} {j[1].cell_id} seed{j[2]}"  # noqa: E731
    done, attempts = 0, {j: 0 for j in jobs}
    consecutive = {m: 0 for m in stops}          # transient run failures in a row, per model
    systemic: dict[str, str] = {}                # model -> error that needs a fix
    rate_limited: dict[str, str] = {}            # model -> sustained-429 stop (resumable)
    budget_stop = None
    deadline_hit = False
    queue = list(jobs)
    # Runs in flight per model = that model's current in-flight limit (its rate
    # gate's, which falls back under 429s/provider errors), so each model gets
    # its own share of threads; total threads = sum of the per-model maxima.
    by_model = llm["max_inflight_by_model"]
    model_max = {m: int(by_model.get(m, llm["max_inflight"])) for m in stops}

    def cap(m):
        if client is not None and m in getattr(client, "gates", {}):
            return client.gates[m].limit
        return model_max[m]

    workers = args.concurrency or max(llm["concurrency"], sum(model_max.values()))
    pool = ThreadPoolExecutor(max_workers=workers)
    n_running = {m: 0 for m in stops}
    running: dict = {}
    try:
        while queue or running:
            if deadline and not deadline_hit and time.time() >= deadline:
                deadline_hit = True
                print(f"deadline {args.deadline} reached: starting no new runs; "
                      f"{len(running)} in-flight run(s) will finish", flush=True)
            while len(running) < workers and not deadline_hit:
                j = next((x for x in queue if not stops[x[0]].is_set() and n_running[x[0]] < cap(x[0])), None)
                if j is None:
                    break
                queue.remove(j)
                attempts[j] += 1
                n_running[j[0]] += 1
                running[pool.submit(one, j)] = j
            if not running:
                break
            finished, _ = wait(running, return_when=FIRST_COMPLETED, timeout=30)
            for fut in finished:
                j = running.pop(fut)
                n_running[j[0]] -= 1
                try:
                    fut.result()
                    done += 1
                    consecutive[j[0]] = 0
                    print(f"[{done}/{len(jobs)}] done {tag(j)}", flush=True)
                except StopRequested as e:
                    print(f"paused {tag(j)} ({e}); checkpoint kept", flush=True)
                except TransientAPIError as e:
                    consecutive[j[0]] += 1
                    kept = partial_progress(run_path(exp, *j))
                    print(f"transient failure {tag(j)} after {kept} rounds: {e}", flush=True)
                    if consecutive[j[0]] >= BREAKER_CONSECUTIVE:
                        print(f"circuit breaker: {consecutive[j[0]]} transient failures in a row on {j[0]}; "
                              f"stopping {j[0]} (other models continue)", flush=True)
                        stops[j[0]].set()
                    elif attempts[j] <= REQUEUES:
                        queue.append(j)        # resumes from its checkpoint
                except (BudgetExceeded, KeysExhausted) as e:
                    # Addendum 2 §2/§6: a cap or an empty key pool is a clean, resumable stop.
                    budget_stop = f"{type(e).__name__}: {e}"
                    print(f"STOP ({tag(j)}): {budget_stop}; in-flight runs pause after their current round",
                          flush=True)
                    stop_all()
                except RateLimited as e:
                    if not stops[j[0]].is_set():
                        rate_limited[j[0]] = str(e)
                        print(f"RATE LIMITED {tag(j)}: {e}; stopping {j[0]} (other models continue)", flush=True)
                        stops[j[0]].set()
                except (APIError, ReplayMismatch) as e:
                    if not stops[j[0]].is_set():
                        systemic[j[0]] = f"{type(e).__name__}: {e}"
                        print(f"SYSTEMIC ERROR on {tag(j)}: {systemic[j[0]]}; stopping {j[0]} "
                              "(other models continue)", flush=True)
                        stops[j[0]].set()
    except KeyboardInterrupt:
        print("\ninterrupted: in-flight runs will pause after their current round "
              "(Ctrl-C again to quit immediately; completed rounds are already on disk)")
        stop_all()
        try:
            wait(running)
        except KeyboardInterrupt:
            pass
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    remaining = [j for j in jobs if resolve_run(exp, *j) is None]
    if client:
        print(f"spend: {client.spent:.4f} cumulative for {exp.name} "
              f"({client.transient_failures} transient failed attempts this invocation)")
        print("key status: " + ", ".join(f"{a}: {'retired' if v['retired'] else 'live'}"
                                         for a, v in client.pool.status().items()))
        print("429s this invocation: " + ", ".join(f"{m}: {g.rate_limits}" for m, g in client.gates.items()))
        print("in-flight fallbacks: " + ", ".join(f"{m}: {g.fallbacks} (limit now {g.limit}/{g.max_inflight})"
                                                  for m, g in client.gates.items()))
    if budget_stop:
        print(f"stopped cleanly: {budget_stop}")
    if deadline_hit:
        print(f"stopped at deadline {args.deadline}")
    if remaining:
        part = sum(1 for j in remaining if partial_progress(run_path(exp, *j)))
        print(f"{len(remaining)} run(s) incomplete ({part} with checkpoints). "
              "Rerun the same command to resume.")
    for m, msg in rate_limited.items():
        print(f"{m} stopped on sustained rate limiting ({msg}); rerun later to resume")
    if systemic:
        for m, msg in systemic.items():
            print(f"fix before rerunning {m}: {msg}")
        sys.exit(1)
    sys.exit(2 if remaining else 0)


if __name__ == "__main__":
    main()
