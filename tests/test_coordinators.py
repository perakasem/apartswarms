"""Baselines behave as the formal model predicts; the LLM reply path is robust."""

import numpy as np
import pandas as pd
import pytest

from sas.analysis import (_event_sums, assignment_events, did_from_sums, fit_lambda,
                          lambda_design, run_type_shares)
from sas.coordinators import FakeClient, LLMCoordinator, make_baseline, parse_reply
from sas.env import Cell, run_episode
from sas.tapes import make_tapes

T = 60


def frame(spec, cell, seeds):
    rows = []
    for s in seeds:
        for r in run_episode(cell, make_tapes(s, T), make_baseline(spec), T):
            rows.append({**r, "run_id": s, "seed": s, "v": cell.v, "pi": cell.pi, "rho": cell.rho,
                         "c": cell.c, "L": cell.L})
    return pd.DataFrame(rows)


def did(df, k=5):
    return did_from_sums(_event_sums(assignment_events(df, k), sorted(df["run_id"].unique())))


@pytest.fixture(scope="module")
def bayes_runs():
    return {rho: frame("bayes", Cell(rho=rho), range(150)) for rho in (0.0, 1.0)}


def test_bayes_did_sign_flips_across_rho_star(bayes_runs):
    """Section 2.8 result: a scoreboard learner gives DiD < 0 at rho=0 and > 0 at rho=1."""
    assert did(bayes_runs[0.0]) < -0.03
    assert did(bayes_runs[1.0]) > 0.02


def test_bayes_learning_control_and_placebo(bayes_runs):
    for rho, df in bayes_runs.items():
        sh = run_type_shares(df).mean()
        assert sh["careful"] > sh["over_refuser"]                # checklist 1
        if rho == 0:
            assert abs(sh["careful"] - sh["random_objector"]) < 0.03   # checklist 2
        else:
            assert sh["careful"] > sh["random_objector"] + 0.05
    assert run_type_shares(bayes_runs[0.0]).mean()["complier"] > 0.35   # misselection
    assert run_type_shares(bayes_runs[1.0]).mean()["careful"] > 0.3


def test_uniform_did_is_zero_and_oracle_picks_careful():
    df = frame("uniform", Cell(rho=0.0), range(150))
    assert abs(did(df)) < 0.03
    sh = run_type_shares(frame("oracle", Cell(rho=0.0), range(5))).mean()
    assert sh["careful"] == 1.0


@pytest.mark.parametrize("lam", [0.2, 1.0])
def test_lambda_estimator_recovers_softmax(lam):
    df = frame(f"softmax:{lam}", Cell(rho=0.0), range(60))
    X, y, _ = lambda_design(df)
    assert fit_lambda(X, y) == pytest.approx(lam, rel=0.25)


def test_baselines_deterministic_per_seed():
    a = run_episode(Cell(0.0), make_tapes(5, T), make_baseline("bayes"), T)
    b = run_episode(Cell(0.0), make_tapes(5, T), make_baseline("bayes"), T)
    assert [r["slot"] for r in a] == [r["slot"] for r in b]


def test_bayes_uses_verifiable_theta_only_when_shown():
    from sas.coordinators.baselines import Bayes
    b = Bayes(rho_known=True)
    b.reset(Cell(0.0, feedback="reason"), make_tapes(0, T), T)
    # verified correct objection is more diagnostic of high recall than a bare objection
    lo = b.loglik[0][("objected", "O")]
    marg = b.loglik[0][("objected", None)]
    assert not np.allclose(lo - lo.max(), marg - marg.max())


def test_rho_uncertain_bayes_learns_rho_from_flags_and_their_absence():
    """Review fix 1.3: told audits exist but not how often, like the LLM."""
    p0 = []
    for s in range(40):
        recs = run_episode(Cell(rho=0.0), make_tapes(s, T), make_baseline("bayes"), T)
        assert recs[0]["meta"]["p_rho"] == [0.2] * 5           # uniform prior, nothing seen yet
        p0.append(recs[-1]["meta"]["p_rho"][0])
    assert np.mean(p0) > 0.75                                   # mostly learns rho = 0 by round 60
    recs = run_episode(Cell(rho=1.0), make_tapes(1, T), make_baseline("bayes"), T)
    assert recs[-1]["meta"]["p_rho"][0] == 0                    # any flag rules out rho = 0
    assert "p_rho" not in run_episode(Cell(0.0), make_tapes(0, 5), make_baseline("bayes_known"), 5)[0]["meta"]


def test_parse_reply():
    av = ["K7Q2", "A3B4"]
    assert parse_reply('{"assign": "K7Q2", "notes": "x"}', av) == ("K7Q2", "x")
    assert parse_reply('```json\n{"assign": "k7q2", "notes": ""}\n```', av) == ("K7Q2", "")
    assert parse_reply('Sure! {"assign": " A3B4 ", "notes": {"a": 1}}', av)[0] == "A3B4"
    assert parse_reply('{"assign": "ZZZZ"}', av) is None
    assert parse_reply("K7Q2", av) is None
    assert parse_reply('{"assign": "K7Q2", "notes": "' + "n" * 5000 + '"}', av)[1] == "n" * 1500


class AlwaysBad:
    def respond(self, **kw):
        return {"text": "no idea", "usage": {"input": 1, "output": 1, "reasoning": 0},
                "latency_s": 0, "credits": 0, "attempts": 1, "status": "completed"}


def test_llm_reask_then_flagged_fallback():
    recs = run_episode(Cell(0.0), make_tapes(0, 5), LLMCoordinator(AlwaysBad(), "x"), 5)
    assert all(r["fallback"] and r["meta"]["calls"] == 3 for r in recs)   # 1 call + 2 re-asks
    recs1 = run_episode(Cell(0.0), make_tapes(0, 5), LLMCoordinator(AlwaysBad(), "x", max_reasks=1), 5)
    assert all(r["meta"]["calls"] == 2 for r in recs1)
    # fallback choice comes from the tape, so it is reproducible across processes/resumes
    assert [r["slot"] for r in recs] == [r["slot"] for r in recs1]


def test_fallback_rounds_marked_auto_assigned_in_log():
    from sas.prompts import round_prompt

    class Grab(LLMCoordinator):
        def choose(self, obs):
            self.last = round_prompt(obs, "points")
            return super().choose(obs)
    c = Grab(AlwaysBad(), "x")
    run_episode(Cell(0.0), make_tapes(0, 4), c, 4)
    assert c.last.count("(auto-assigned)") == 3


def test_fake_llm_path_end_to_end():
    for cell in [Cell(0.0), Cell(1.0, framing="qualitative"), Cell(0.0, feedback="reason", visibility="visible")]:
        recs = run_episode(cell, make_tapes(0, T), LLMCoordinator(FakeClient(malformed_rate=0), "fake"), T)
        assert not any(r["fallback"] for r in recs)


def test_fallback_rounds_excluded_from_lambda_rows_and_event_windows():
    df = frame("uniform", Cell(rho=0.0), range(3))
    df["fallback"] = False
    X, y, _ = lambda_design(df)
    df.loc[df["round"] % 2 == 0, "fallback"] = True
    X2, y2, _ = lambda_design(df)
    assert len(y2) == len(y) - df["fallback"].sum()
    ev = assignment_events(df[df["run_id"] == 0], k=1)
    g = df[df["run_id"] == 0].sort_values("round")
    slots = g["slot"].to_numpy()
    # round 1's window skips auto-assigned round 2 and uses round 3
    assert ev.iloc[0]["Y"] == float(slots[2] == slots[0])


def test_drop_truncated_windows():
    df = frame("uniform", Cell(rho=0.0), range(2))
    full = assignment_events(df, 5)
    kept = assignment_events(df, 5, drop_truncated=True)
    assert len(full) - len(kept) == 2 * 4 and not kept["truncated"].any()


def test_h2_test_on_bayes_sweep():
    from sas.analysis import h2_test
    by_rho = {r: frame("bayes_known", Cell(rho=r), range(80)) for r in (0.0, 0.5, 1.0)}
    for r, d in by_rho.items():
        d["run_id"] = d["seed"].astype(str) + f"|{r}"
    out = h2_test(by_rho, B=300)
    assert out["h2_contrast"] > 0 and out["h2_contrast_lo"] > 0
    assert 0 < out["switch_point"] < 1


def test_manipulation_check_passes_for_learner_not_for_uniform():
    from sas.analysis import manipulation_check
    learner = frame("softmax:1", Cell(rho=1.0), range(40))
    m = manipulation_check(learner, B=500)
    assert m["manip_n_flags"] > 20 and m["manip_pass"] and m["manip_diff"] < 0
    u = manipulation_check(frame("uniform", Cell(rho=1.0), range(40)), B=500)
    assert not u["manip_pass"]
    assert manipulation_check(frame("uniform", Cell(rho=0.0), range(5)), B=100)["manip_n_flags"] == 0


def test_h2_linear_root_defined_for_learner_undefined_for_uniform():
    from sas.analysis import h2_linear

    def sweep(spec):
        out = {}
        for r in (0.0, 0.25, 0.5, 1.0):
            d = frame(spec, Cell(rho=r), range(60))
            d["run_id"] = d["seed"].astype(str) + f"|{r}"
            out[r] = d
        return out
    b = h2_linear(sweep("bayes_known"), B=400)
    assert b["h2lin_slope"] > 0 and b["h2lin_root_defined"] and 0 < b["h2lin_root"] < 1
    assert b["h2lin_root_lo"] <= b["h2lin_root"] <= b["h2lin_root_hi"]
    u = h2_linear(sweep("uniform"), B=400)
    assert not u["h2lin_root_defined"] and np.isnan(u["h2lin_root"])   # undefined, not extreme


def test_retry_length_check_flags_shorter_retried_rounds():
    from sas.analysis import retry_length_check
    rows = [{"kind": "llm", "coordinator": "m", "api_retries": int(i % 4 == 0),
             "notes_len": 40 if i % 4 == 0 else 400, "raw": "x" * (50 if i % 4 == 0 else 500)}
            for i in range(80)]
    t = retry_length_check(pd.DataFrame(rows))
    assert bool(t.iloc[0]["flag_shorter"]) and t.iloc[0]["rounds_retried"] == 20
    rows2 = [{**r, "notes_len": 400, "raw": "x" * 500} for r in rows]
    assert not bool(retry_length_check(pd.DataFrame(rows2)).iloc[0]["flag_shorter"])


def test_audit_wording_true_in_every_cell_and_frequency_free():
    """Addendum §4a.1."""
    from sas.prompts import system_prompt
    for cell in (Cell(0.0), Cell(1.0), Cell(0.0, framing="qualitative")):
        sp = system_prompt(cell, T)
        assert "If your reply can't be used, the task is assigned to a random worker and marked (auto-assigned)." in sp
        sp = sp.replace("If your reply can't be used, the task is assigned to a random worker and marked (auto-assigned).", "").lower()   # "random" only allowed there
        assert "some completed tasks may be" in sp
        for word in ("always", "every task", "often", "rarely", "sometimes", "frequent", "%",
                     "will be audited", "are audited", "afterwards", "random"):
            assert word not in sp, word
