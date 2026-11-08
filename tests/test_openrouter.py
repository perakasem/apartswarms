"""OpenRouter client and key pool against mocked HTTP (no network), Addendum 2."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from sas.api import BudgetExceeded, KeysExhausted, ReasoningControlError, TransientAPIError
from sas.openrouter import KeyPool, OpenRouterClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
KEYS = ["sk-or-v1-aaaaSECRET1", "sk-or-v1-bbbbSECRET2", "sk-or-v1-ccccSECRET3"]
ROUTES = {"m": {"slug": "vendor/model-x", "provider": "deepinfra/fp8", "reasoning": {"effort": "none"},
                "price_in": 0.1, "price_out": 0.2}}


def ok_body(text='{"assign": "A", "notes": ""}', cost=0.001, reasoning=0, provider="DeepInfra",
            model="vendor/model-x"):
    return {"id": "gen-1", "model": model, "provider": provider,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 20, "total_tokens": 1020, "cost": cost,
                      "completion_tokens_details": {"reasoning_tokens": reasoning}}}


def transport(balances: dict, chat):
    """balances: key -> limit_remaining; chat(request, key) -> httpx.Response."""
    def handler(request: httpx.Request):
        key = request.headers["authorization"].split(" ", 1)[1]
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {"limit_remaining": balances.get(key), "usage": 0}})
        if request.url.path.endswith("/credits"):
            return httpx.Response(404)
        return chat(request, key)
    return httpx.MockTransport(handler)


def make(balances, chat, tmp_path, **kw):
    t = transport(balances, chat)
    pool = KeyPool(KEYS, transport=t)
    pool.refresh()
    client = OpenRouterClient(routes=ROUTES, pool=pool, max_usd=kw.pop("max_usd", 10.0),
                              global_max_usd=kw.pop("global_max_usd", 140.0),
                              ledger_path=tmp_path / "ledger.jsonl", global_ledger_path=tmp_path / "global.jsonl",
                              transport=t, sleep=lambda s: None, **kw)
    return pool, client


def test_selects_key_with_most_remaining_and_tracks_local_spend(tmp_path):
    pool, client = make({KEYS[0]: 10.0, KEYS[1]: 30.0, KEYS[2]: 20.0},
                        lambda r, k: httpx.Response(200, json=ok_body(cost=15.0)), tmp_path)
    assert pool.acquire() == "k2"
    r = client.respond(model="m", instructions="s", input="u")
    assert r["key_alias"] == "k2"
    assert pool.acquire() == "k3"                      # k2 now 15 < k3 20


def test_selection_is_thread_safe(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    pool, client = make({KEYS[0]: 50.0, KEYS[1]: 50.0, KEYS[2]: 50.0},
                        lambda r, k: httpx.Response(200, json=ok_body(cost=0.5)), tmp_path, max_usd=100.0)
    pool.refresh_every = 10_000   # the mock /key does not reflect spend, so no mid-test refresh
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(lambda _: client.respond(model="m", instructions="s", input="u"), range(60)))
    spent = sum(pool.spent_local.values())
    assert abs(spent - 30.0) < 1e-9                    # no lost updates
    assert max(pool.spent_local.values()) - min(pool.spent_local.values()) <= 1.0   # spread across keys


def test_retirement_at_threshold(tmp_path):
    pool, client = make({KEYS[0]: 1.5, KEYS[1]: 3.0, KEYS[2]: None},
                        lambda r, k: httpx.Response(200, json=ok_body(cost=1.2)), tmp_path)
    assert "k1" in pool.retired                        # below $2 at refresh
    pool.retire("k3", "test")
    client.respond(model="m", instructions="s", input="u")   # k2: 3.0 - 1.2 = 1.8 < 2
    assert "k2" in pool.retired


def test_402_retries_same_call_on_next_key_without_counting(tmp_path):
    seen = []

    def chat(request, key):
        seen.append((key, json.loads(request.content)))
        if key == KEYS[1]:
            return httpx.Response(402, json={"error": {"code": 402, "message": "Insufficient credits",
                                                       "metadata": {"limit_source": "openrouter_credits"}}})
        return httpx.Response(200, json=ok_body())
    pool, client = make({KEYS[0]: 10.0, KEYS[1]: 30.0, KEYS[2]: 20.0}, chat, tmp_path, max_retries=0)
    r = client.respond(model="m", instructions="s", input="u")
    assert [k for k, _ in seen] == [KEYS[1], KEYS[2]]
    assert seen[0][1] == seen[1][1]                    # the same call
    assert r["attempts"] == 1 and r["key_alias"] == "k3" and "k2" in pool.retired


def test_all_keys_exhausted_raises(tmp_path):
    def chat(request, key):
        return httpx.Response(402, json={"error": {"code": 402, "message": "Insufficient credits"}})
    pool, client = make({k: 10.0 for k in KEYS}, chat, tmp_path)
    with pytest.raises(KeysExhausted):
        client.respond(model="m", instructions="s", input="u")
    assert set(pool.retired) == {"k1", "k2", "k3"}


def test_keys_never_in_logs_records_or_errors(tmp_path):
    recs = []

    def chat(request, key):
        if key == KEYS[1]:   # an error body that echoes the key back
            return httpx.Response(401, json={"error": {"code": 401, "message": f"bad key {key}"}})
        return httpx.Response(400, json={"error": {"code": 400, "message": f"bad request for {key}"}})
    pool, client = make({KEYS[0]: 10.0, KEYS[1]: 30.0, KEYS[2]: 20.0}, chat, tmp_path)
    with pytest.raises(Exception) as e:
        client.respond(model="m", instructions="s", input="u", on_attempt=recs.append)
    blob = json.dumps(recs) + str(e.value) + (tmp_path / "ledger.jsonl").read_text() + json.dumps(pool.status())
    for k in KEYS:
        assert k not in blob and k[-7:] not in blob
    assert "[k2]" in blob or "k2" in blob


def test_request_pins_provider_disables_reasoning_and_has_no_key(tmp_path):
    seen = []
    pool, client = make({k: 10.0 for k in KEYS},
                        lambda r, k: (seen.append(json.loads(r.content)), httpx.Response(200, json=ok_body()))[1],
                        tmp_path)
    client.respond(model="m", instructions="sys", input="usr", temperature=1.0, max_output_tokens=512)
    p = seen[0]
    assert p["provider"] == {"order": ["deepinfra/fp8"], "allow_fallbacks": False, "require_parameters": True}
    assert p["reasoning"] == {"effort": "none"} and p["model"] == "vendor/model-x"
    assert p["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
    assert not any(k in json.dumps(p) for k in KEYS)
    line = json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])
    assert line["usd"] == 0.001 and line["key_alias"] in ("k1", "k2", "k3") and line["provider"] == "DeepInfra"


def test_reasoning_and_provider_mismatch_refused(tmp_path):
    _, c = make({k: 10.0 for k in KEYS}, lambda r, k: httpx.Response(200, json=ok_body(reasoning=40)), tmp_path)
    with pytest.raises(ReasoningControlError):
        c.respond(model="m", instructions="s", input="u")
    _, c = make({k: 10.0 for k in KEYS}, lambda r, k: httpx.Response(200, json=ok_body(provider="Fireworks")),
                tmp_path)
    with pytest.raises(Exception, match="pinned"):
        c.respond(model="m", instructions="s", input="u")


def test_504_retried_then_transient(tmp_path):
    _, c = make({k: 10.0 for k in KEYS}, lambda r, k: httpx.Response(504), tmp_path, max_retries=2)
    with pytest.raises(TransientAPIError):
        c.respond(model="m", instructions="s", input="u")


def test_dollar_caps(tmp_path):
    _, c = make({k: 10.0 for k in KEYS}, lambda r, k: httpx.Response(200, json=ok_body(cost=6.0)), tmp_path,
                max_usd=10.0, global_max_usd=11.0)
    c.respond(model="m", instructions="s", input="u")
    c.respond(model="m", instructions="s", input="u")          # 12 spent
    with pytest.raises(BudgetExceeded):
        c.respond(model="m", instructions="s", input="u")


def test_cache_key_has_host_and_route_not_key(tmp_path, monkeypatch):
    import sas.grid as grid
    from sas.env import Cell
    monkeypatch.setattr(grid, "RUNS", tmp_path / "runs")
    base = dict(name="t", T=20, models=["qwen3.5-397b"], stage="confirmatory")
    orx = grid.Experiment(**base, llm={"api": "openrouter", "temperature": 1.0})
    b = grid.run_path(orx, "qwen3.5-397b", Cell(0.0), 0)
    routes = grid.Experiment.routes(orx)
    moved = {**routes, "qwen3.5-397b": {**routes["qwen3.5-397b"], "provider": "atlas-cloud/fp8"}}
    monkeypatch.setattr(grid.Experiment, "routes", lambda self: moved)
    assert grid.run_path(orx, "qwen3.5-397b", Cell(0.0), 0) != b   # never mix providers
    monkeypatch.undo()
    monkeypatch.setattr(grid, "RUNS", tmp_path / "runs")
    monkeypatch.setenv("OPENROUTER_API_KEYS", "x,y,z")
    assert grid.run_path(orx, "qwen3.5-397b", Cell(0.0), 0) == b   # keys are not an input


def test_runner_exits_2_when_keys_exhausted(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("name: broke\nstage: smoke\nT: 20\nfactors: {rho: [0.0]}\nseeds: [0, 1, 2]\nmodels: [fake-broke]\n")
    env = {**os.environ, "SAS_RESULTS": str(tmp_path)}
    r = subprocess.run([sys.executable, "scripts/run_experiment.py", "--config", str(cfg)], cwd=ROOT,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "stopped cleanly: KeysExhausted" in r.stdout


def test_deadline_parsing():
    import run_experiment
    with pytest.raises(SystemExit):
        run_experiment.parse_deadline("00:00")


def test_load_keys_strips_per_key_quotes(monkeypatch):
    from sas.openrouter import load_keys
    monkeypatch.setenv("OPENROUTER_API_KEYS", '"sk-or-v1-a", \'sk-or-v1-b\' ,sk-or-v1-c,')
    assert load_keys() == ["sk-or-v1-a", "sk-or-v1-b", "sk-or-v1-c"]


def test_ledger_tolerates_torn_line(tmp_path):
    from sas.api import ledger_total
    ledger = tmp_path / "l.jsonl"
    ledger.write_text(json.dumps({"credits": 1.5}) + "\n" + '{"credits": 2.')
    assert ledger_total(ledger) == 1.5


def test_429_retries_only_that_call_without_pausing_the_model(tmp_path):
    responses = iter([httpx.Response(429, headers={"retry-after": "1"}), httpx.Response(200, json=ok_body())])
    slept = []
    _, client = make({k: 50.0 for k in KEYS}, lambda r, k: next(responses), tmp_path)
    client._sleep = slept.append
    r = client.respond(model="m", instructions="s", input="u")
    gate = client.gates["m"]
    assert r["attempts"] == 2 and gate.rate_limits == 1 and gate.rps == 8.0
    assert len(slept) == 1 and 2.0 <= slept[0] <= 10.0          # short jittered wait, >= Retry-After


def test_occasional_429s_never_stop_a_model(tmp_path):
    n = {"i": 0}

    def chat(r, k):
        n["i"] += 1
        return httpx.Response(429) if n["i"] % 10 == 0 else httpx.Response(200, json=ok_body(cost=0.0001))
    _, client = make({k: 50.0 for k in KEYS}, chat, tmp_path)
    client.gates["m"].rps = 1e6
    for _ in range(300):                 # ~10% 429: the old 3-cycle rule stopped here
        client.respond(model="m", instructions="s", input="u")
    assert client.gates["m"].rate_limits >= 30


def test_sustained_429_raises_rate_limited(tmp_path):
    from sas.api import RateLimited
    _, client = make({k: 50.0 for k in KEYS}, lambda r, k: httpx.Response(429), tmp_path)
    with pytest.raises(RateLimited):
        client.respond(model="m", instructions="s", input="u")


def test_gate_saturation_window():
    from sas.api import RateGate
    g = RateGate(window=10, saturation=0.5)
    for _ in range(5):
        g.ok()
    assert not any(g.rate_limited() for _ in range(5))   # 5/10: not over half
    assert g.rate_limited()                              # 6/10


def test_runner_contains_rate_limit_to_one_model(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("name: contain\nstage: smoke\nT: 20\nfactors: {rho: [0.0]}\nseeds: [0, 1, 2]\n"
                   "models: [fake-ratelimited, fake]\n")
    env = {**os.environ, "SAS_RESULTS": str(tmp_path)}
    r = subprocess.run([sys.executable, "scripts/run_experiment.py", "--config", str(cfg)], cwd=ROOT,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2, r.stdout + r.stderr                # resumable, not systemic
    assert "RATE LIMITED fake-ratelimited" in r.stdout
    assert r.stdout.count("done fake ") == 3                     # the other model finished every run
    assert "stopped on sustained rate limiting" in r.stdout


def test_inflight_limit_falls_back_and_restores():
    from sas.api import RateGate
    g = RateGate(rps=1e6, max_inflight=32, floor=16, health_window=50)
    for i in range(50):
        g.ok() if i % 5 else g.rate_limited()      # 20% errors > 10%
    assert g.limit == 16 and g.fallbacks == 1
    for _ in range(50):
        g.ok()                                     # clean window: <= 2%
    assert g.limit == 32


def test_client_sets_per_model_inflight(tmp_path):
    routes = {**ROUTES, "q": {**ROUTES["m"]}}
    pool = KeyPool(KEYS, transport=transport({}, lambda r, k: httpx.Response(200, json=ok_body())))
    c = OpenRouterClient(routes=routes, pool=pool, max_usd=1, global_max_usd=1, ledger_path=None,
                         global_ledger_path=None, max_inflight=16, inflight_by_model={"q": 32}, inflight_floor=16)
    assert (c.gates["q"].limit, c.gates["q"].floor) == (32, 16)
    assert (c.gates["m"].limit, c.gates["m"].floor) == (16, None)
