"""Adaption client against a mocked transport (no network)."""

import json

import httpx
import pytest

from sas.adaption import (AdaptionClient, AdaptionError, BudgetExceeded, RateGate,
                          ReasoningControlError, TransientAPIError, ledger_total)


def ok_body(text='{"assign": "A"}', reasoning=0, effort="none", model="qwen3.5-397b", n_in=1000, n_out=10):
    return {"model": model, "status": "completed", "reasoning": {"effort": effort},
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": n_in, "output_tokens": n_out,
                      "output_tokens_details": {"reasoning_tokens": reasoning}}}


def client(handler, **kw):
    seen = []

    def wrapped(request):
        seen.append(json.loads(request.content))
        return handler(request)

    c = AdaptionClient(key="sk-secret", transport=httpx.MockTransport(wrapped),
                       gate=RateGate(rps=1000, pause_s=0.0), sleep=lambda s: None, **kw)
    return c, seen


def test_request_shape_and_text():
    c, seen = client(lambda r: httpx.Response(200, json=ok_body()))
    r = c.respond(model="qwen3.5-397b", instructions="sys", input="hi", max_output_tokens=64, temperature=1.0)
    assert r["text"] == '{"assign": "A"}'
    assert seen[0]["reasoning"] == {"effort": "none"}
    assert seen[0]["temperature"] == 1.0 and seen[0]["max_output_tokens"] == 64
    assert r["credits"] == pytest.approx((1000 * 0.55 + 10 * 3.5) / 1e6)


def test_no_server_side_state_flags_on_every_request():
    """Decisions §1.1 / CLAUDE.md invariant 4."""
    c, seen = client(lambda r: httpx.Response(200, json=ok_body()))
    c.respond(model="qwen3.5-397b", instructions="", input="x")
    assert seen[0]["store"] is False and seen[0]["agentic_memory"] is False and seen[0]["background"] is False
    with pytest.raises(AdaptionError):
        c.respond(model="stack:my-stack", instructions="", input="x")


def test_every_attempt_logged_raw():
    """Decisions §1.2: one record per attempt, incl. retries, with full request and raw response."""
    responses = iter([httpx.Response(504, text="gateway timeout"), httpx.Response(200, json=ok_body())])
    c, _ = client(lambda r: next(responses))
    recs = []
    c.respond(model="qwen3.5-397b", instructions="sys", input="prompt", on_attempt=recs.append)
    assert [r["attempt"] for r in recs] == [1, 2] and [r["status"] for r in recs] == [504, 200]
    assert recs[0]["response"] == {"body": "gateway timeout"}
    assert recs[1]["response"]["output"][0]["content"][0]["text"] == '{"assign": "A"}'
    assert recs[1]["request"]["input"] == "prompt" and recs[1]["served_model"] == "qwen3.5-397b"
    assert recs[1]["usage"]["input_tokens"] == 1000 and "latency_s" in recs[1]
    assert "sk-secret" not in json.dumps(recs)


def test_reasoning_control_enforced():
    c, _ = client(lambda r: httpx.Response(200, json=ok_body(reasoning=57)))
    with pytest.raises(ReasoningControlError):
        c.respond(model="qwen3.5-397b", instructions="", input="x")
    c, _ = client(lambda r: httpx.Response(200, json=ok_body(reasoning=None)))
    with pytest.raises(ReasoningControlError):
        c.respond(model="qwen3.5-397b", instructions="", input="x")


def test_model_mismatch_rejected():
    c, _ = client(lambda r: httpx.Response(200, json=ok_body(model="other-model")))
    with pytest.raises(AdaptionError):
        c.respond(model="qwen3.5-397b", instructions="", input="x")


def test_504s_retried_with_backoff_then_succeed(tmp_path):
    responses = iter([httpx.Response(504), httpx.Response(502), httpx.Response(200, json=ok_body())])
    ledger = tmp_path / "l.jsonl"
    c, seen = client(lambda r: next(responses), ledger_path=ledger)
    r = c.respond(model="qwen3.5-397b", instructions="", input="x" * 3000)
    assert r["attempts"] == 3 and len(seen) == 3
    lines = [json.loads(x) for x in ledger.read_text().splitlines()]
    assert [x.get("uncertain", False) for x in lines] == [True, True, False]   # failures charged
    assert c.transient_failures == 2


def test_persistent_5xx_raises_transient_after_max_retries():
    calls = []
    sleeps = []

    def h(r):
        calls.append(1)
        return httpx.Response(504)
    c = AdaptionClient(key="k", transport=httpx.MockTransport(h), gate=RateGate(rps=1000),
                       max_retries=4, sleep=sleeps.append, backoff_base_s=5, backoff_max_s=120)
    with pytest.raises(TransientAPIError):
        c.respond(model="qwen3.5-397b", instructions="", input="x")
    assert len(calls) == 5
    assert all(2.5 <= s <= 120 for s in sleeps) and sleeps[-1] > sleeps[0]   # exponential, jittered


def test_timeouts_are_transient():
    def h(r):
        raise httpx.ReadTimeout("slow")
    c, _ = client(h, max_retries=1)
    with pytest.raises(TransientAPIError):
        c.respond(model="qwen3.5-397b", instructions="", input="x")


def test_4xx_not_retried():
    calls = []

    def h(r):
        calls.append(1)
        return httpx.Response(401, text="nope")
    c, _ = client(h)
    with pytest.raises(AdaptionError) as e:
        c.respond(model="qwen3.5-397b", instructions="", input="x")
    assert not isinstance(e.value, TransientAPIError) and len(calls) == 1


def test_ledger_tolerates_torn_line(tmp_path):
    ledger = tmp_path / "l.jsonl"
    ledger.write_text(json.dumps({"credits": 1.5}) + "\n" + '{"credits": 2.')
    assert ledger_total(ledger) == 1.5


def test_429_backs_off_and_halves_rate():
    responses = iter([httpx.Response(429, headers={"retry-after": "0"}), httpx.Response(200, json=ok_body())])
    c, _ = client(lambda r: next(responses))
    rate = c.gate.rps
    c.respond(model="qwen3.5-397b", instructions="", input="x")
    assert c.gate.cycles == 1 and c.gate.rps == rate / 2


def test_errors_redact_key():
    c, _ = client(lambda r: httpx.Response(400, text="bad key sk-secret"))
    with pytest.raises(AdaptionError) as e:
        c.respond(model="qwen3.5-397b", instructions="", input="x")
    assert "sk-secret" not in str(e.value)


def test_budget_is_cumulative_via_ledger(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"credits": 5.0}) + "\n")
    c, _ = client(lambda r: httpx.Response(200, json=ok_body()), max_credits=5.0, ledger_path=ledger)
    assert c.spent == 5.0
    with pytest.raises(BudgetExceeded):
        c.respond(model="qwen3.5-397b", instructions="", input="x")


def test_ledger_appends(tmp_path):
    ledger = tmp_path / "l.jsonl"
    c, _ = client(lambda r: httpx.Response(200, json=ok_body()), ledger_path=ledger)
    c.respond(model="qwen3.5-397b", instructions="", input="x")
    c.respond(model="qwen3.5-397b", instructions="", input="x")
    assert ledger_total(ledger) == pytest.approx(2 * (1000 * 0.55 + 10 * 3.5) / 1e6)
