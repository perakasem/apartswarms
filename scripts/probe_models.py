"""Pre-flight for each coordinator model, before any grid run (costs a few
hundredths of a credit). Sends real coordinator prompts, including the
longest one a run can produce (round T, reason feedback, task visible), and
checks for each reply:
  * HTTP OK and the reasoning control honoured (reasoning_tokens == 0)
  * the reply parses to a valid worker label without a re-ask
  * the temperature setting is accepted
Writes results/probes/<model>.json; run_experiment.py refuses live models
without a passing probe.

  uv run scripts/probe_models.py --config configs/confirmatory.yaml --model qwen3.5-397b
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.adaption import AdaptionClient, AdaptionError  # noqa: E402
from sas.coordinators import Uniform, parse_reply  # noqa: E402
from sas.env import Cell, Observation, run_episode  # noqa: E402
from sas.grid import RESULTS, ROOT, load_experiment  # noqa: E402
from sas.prompts import round_prompt, system_prompt  # noqa: E402
from sas.tapes import make_tapes  # noqa: E402

OUT = RESULTS / "probes"


def sample_prompts(T: int) -> list[tuple[str, Cell, Observation]]:
    """Capture real observations from uniform runs: first, middle and last
    round, for the primary cell and the longest-prompt cell."""
    picks = []
    for name, cell in [("primary", Cell(rho=0.0)),
                       ("longest", Cell(rho=1.0, feedback="reason", visibility="visible", tone="preachy")),
                       ("qualitative", Cell(rho=0.0, framing="qualitative"))]:
        seen = []

        class Rec(Uniform):
            def choose(self, obs):
                seen.append(obs)
                return super().choose(obs)

        run_episode(cell, make_tapes(12345, T), Rec(), T)
        rounds = [0, T - 1] if name != "qualitative" else [T // 2]
        picks += [(f"{name}-r{seen[i].round}", cell, seen[i]) for i in rounds]
    return picks


def recovery_passed() -> tuple[bool, str]:
    """Addendum §4a.4: the probe runs only after Stage 0 recovery has passed
    at full size (>= 100 studies, coverage >= 90%)."""
    path = RESULTS / "recovery.json"
    if not path.exists():
        return False, "no results/recovery.json; run scripts/recover.py"
    r = json.loads(path.read_text())
    if r.get("studies", 0) < 100:
        return False, f"recovery.json has only {r.get('studies')} studies; rerun scripts/recover.py"
    if not r.get("passed"):
        return False, f"parameter recovery failed (coverage {r.get('coverage'):.2f} < {r.get('gate')})"
    return True, f"parameter recovery passed (coverage {r['coverage']:.2f}, {r['studies']} studies)"


def wall_time(cfg_path: Path, latency: dict, inflight: int | None = None) -> str:
    """Projected wall time: per model, runs in waves of `inflight` (default: the
    config's max_inflight), each run T sequential calls at the measured median
    latency; models run in parallel. Ignores retries and rate limits."""
    e = load_experiment(cfg_path)
    st = e.llm_settings()
    per = {}
    for m in e.models:
        if m not in latency:
            continue
        runs = sum(len(e.seeds_for(c)) for c in e.cells())
        waves = -(-runs // (inflight or st["max_inflight"]))
        per[m] = waves * e.T * latency[m]
    if not per:
        return "n/a"
    worst = max(per, key=per.get)
    return (f"~{max(per.values()) / 3600:.1f} h (bottleneck {worst}; "
            + ", ".join(f"{m} {v / 3600:.1f} h" for m, v in per.items()) + ")")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--model", action="append")
    ap.add_argument("--repeats", type=int, default=2, help="calls per sample prompt")
    ap.add_argument("--wall-time-only", action="store_true",
                    help="print projected wall times from saved probe results and exit (no API calls)")
    args = ap.parse_args()
    if args.wall_time_only:
        wall_times_from_saved()
        return
    ok, msg = recovery_passed()
    print(msg)
    if not ok:
        sys.exit("refusing to probe before Stage 0 parameter recovery passes")
    exp = load_experiment(args.config)
    llm = exp.llm_settings()
    api = llm["api"]
    OUT.mkdir(parents=True, exist_ok=True)
    aliases = [None]
    if api == "openrouter":
        from sas.openrouter import KeyPool, OpenRouterClient, load_keys
        pool = KeyPool(load_keys())
        status = pool.refresh()
        print("keys: " + ", ".join(
            f"{a}: {'RETIRED ' + v['retired'] if v['retired'] else ('balance unknown' if v['remaining'] == float('inf') else '$%.2f' % v['remaining'])}"
            for a, v in status.items()))
        aliases = [a for a, v in status.items() if not v["retired"]]
        if not aliases:
            sys.exit("no usable OpenRouter key")
        client = OpenRouterClient(routes=exp.routes(), pool=pool, max_usd=1.0,
                                  global_max_usd=llm["global_max_usd"],
                                  ledger_path=OUT / "openrouter_probe_ledger.jsonl",
                                  global_ledger_path=RESULTS / "openrouter_ledger.jsonl",
                                  max_retries=llm["max_retries"])
        client.spent = 0.0   # the probe's own cap ($1) is per invocation
    else:
        client = AdaptionClient(max_credits=1.0, ledger_path=OUT / "ledger.jsonl")
        client.spent = 0.0   # the probe cap is per invocation

    latency = {}
    used_keys = set()
    for model in args.model or exp.models:
        results, ok = [], True
        route = exp.routes().get(model, {})
        i = 0
        for name, cell, obs in sample_prompts(exp.T):
            prompt = round_prompt(obs, cell.framing)
            for rep in range(args.repeats):
                prefer = aliases[i % len(aliases)]      # exercise every live key
                i += 1
                rec = {"sample": name, "repeat": rep, "prompt_chars": len(prompt),
                       "system_chars": len(system_prompt(cell, exp.T))}
                t0 = time.monotonic()
                try:
                    kw = {"prefer_key": prefer} if api == "openrouter" else {}
                    r = client.respond(model=model, instructions=system_prompt(cell, exp.T), input=prompt,
                                       max_output_tokens=llm["max_output_tokens"],
                                       temperature=llm["temperature"], **kw)
                    parsed = parse_reply(r["text"], obs.available)
                    # Addendum 2 §3: the probe requires the reasoning-token field to be
                    # present and zero on the pinned provider (the client already refuses
                    # non-zero counts and reasoning text).
                    strict = api != "openrouter" or (r.get("reasoning_field_present") and r["usage"]["reasoning"] == 0)
                    rec.update(ok=parsed is not None and bool(strict), text=r["text"][:300], usage=r["usage"],
                               latency_s=r["latency_s"], credits=r["credits"], status=r["status"],
                               provider=r.get("provider"), key_alias=r.get("key_alias"),
                               served_model=r.get("served_model"),
                               reasoning_field_present=r.get("reasoning_field_present"))
                    used_keys.add(r.get("key_alias"))
                except AdaptionError as e:
                    rec.update(ok=False, error=str(e)[:300], latency_s=time.monotonic() - t0)
                ok &= rec["ok"]
                results.append(rec)
                print(f"{model} {name} #{rep} [{rec.get('key_alias') or '-'}]: {'OK' if rec['ok'] else 'FAIL'} "
                      f"{rec.get('usage', '')} {rec.get('latency_s', 0):.1f}s "
                      f"{rec.get('error', rec.get('text', ''))[:70]!r}", flush=True)
        lats = sorted(r["latency_s"] for r in results if r.get("ok"))
        latency[model] = lats[len(lats) // 2] if lats else None
        report = {"model": model, "api": api, "route": route, "passed": ok, "time": time.time(),
                  "settings": {k: llm[k] for k in ("max_output_tokens", "temperature")},
                  "median_latency_s": latency[model],
                  "max_input_tokens": max((r.get("usage", {}).get("input", 0) for r in results), default=0),
                  "credits": sum(r.get("credits", 0) for r in results),
                  "reasoning_tokens": sorted({str(r.get("usage", {}).get("reasoning")) for r in results}),
                  "results": results}
        (OUT / f"{api}-{model}.json").write_text(json.dumps(report, indent=1))
        unit = "USD" if api == "openrouter" else "credits"
        print(f"==> {model}{' @ ' + route['provider'] if route else ''}: {'PASSED' if ok else 'FAILED'}; "
              f"reasoning tokens {report['reasoning_tokens']}; median latency "
              f"{latency[model] if latency[model] is not None else float('nan'):.1f}s; max input tokens "
              f"{report['max_input_tokens']}; {report['credits']:.5f} {unit}")
        if not ok and api == "openrouter" and any("reasoning" in r.get("error", "") for r in results):
            print(f"STOP: {model} did not run with zero reasoning tokens on {route.get('provider')}. "
                  "Do not substitute a model; ask the team (Addendum 2 §3).")
    if api == "openrouter":
        missing = set(aliases) - used_keys
        print("every live key exercised: " + ("yes" if not missing else f"NO, missing {sorted(missing)}"))
    print_wall_times({m: v for m, v in latency.items() if v})


def print_wall_times(lat: dict) -> None:
    for cfg in ("pilot", "confirmatory"):
        for n in (8, 16):
            print(f"projected wall time, {cfg}, {n} in flight per model: "
                  f"{wall_time(ROOT / 'configs' / f'{cfg}.yaml', lat, n)}")


def wall_times_from_saved(api: str = "openrouter") -> None:
    """--wall-time-only: reuse the saved probe latencies; no API calls."""
    lat = {}
    for f in sorted(OUT.glob(f"{api}-*.json")):
        r = json.loads(f.read_text())
        if r.get("median_latency_s"):
            lat[r["model"]] = r["median_latency_s"]
    print("median latency (s): " + ", ".join(f"{m} {v:.1f}" for m, v in lat.items()))
    print_wall_times(lat)


if __name__ == "__main__":
    main()
