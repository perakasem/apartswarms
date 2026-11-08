"""Run store: cache keys (review fix 1.2), checkpoint/resume (HTTP 504
robustness), seed-range roles (review fix 1.1), and the confirmatory family."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

import sas.grid as grid
from sas.adaption import TransientAPIError
from sas.coordinators import FakeClient, LLMCoordinator
from sas.env import Cell, ReplayMismatch
from sas.grid import Experiment, execute_run, load_experiment, partial_progress, read_run, run_path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(grid, "RUNS", tmp_path / "runs")
    return tmp_path


def exp(**kw):
    base = dict(name="t", T=20, models=["fake"], baselines=["bayes"], stage="secondary",
                llm={"temperature": 1.0, "max_output_tokens": 512})
    base.update(kw)
    return Experiment(**base)


class DiesAfter(FakeClient):
    """Fake client whose process 'dies' (504 storm) after n calls."""
    def __init__(self, n):
        super().__init__(malformed_rate=0)
        self.n = 0
        self.limit = n

    def respond(self, **kw):
        self.n += 1
        if self.n > self.limit:
            raise TransientAPIError("simulated 504")
        return super().respond(**kw)


def llm(client, e):
    s = e.llm_settings()
    return LLMCoordinator(client, "fake", temperature=s["temperature"], max_reasks=s["max_reasks"])


# ------------------------------------------------------------- cache key (1.2)

def test_fingerprint_changes_with_behaviour_not_with_nothing(store):
    cell = Cell(0.0)
    a = run_path(exp(), "fake", cell, 0)
    assert run_path(exp(), "fake", cell, 0) == a                          # deterministic
    assert run_path(exp(llm={"temperature": 0.7}), "fake", cell, 0) != a  # temperature
    assert run_path(exp(llm={"temperature": 1.0, "max_reasks": 1}), "fake", cell, 0) != a
    assert run_path(exp(T=21), "fake", cell, 0) != a                      # horizon
    fp = lambda p: p.parent.parent.name   # .../<fingerprint>/<stage>/seedN.jsonl  # noqa: E731
    assert fp(run_path(exp(), "other-model", cell, 0)) != fp(a)          # model id
    assert fp(run_path(exp(), "baseline-bayes", cell, 0)) != \
        fp(run_path(exp(baselines=["bayes_known"]), "baseline-bayes_known", cell, 0))
    assert a.parent.name == "secondary"                                   # stage directory


def test_prompt_edit_changes_fingerprint(store, monkeypatch):
    import sas.fingerprint as fp
    import sas.prompts as prompts
    a = run_path(exp(), "fake", Cell(0.0), 0)
    fp._llm_fp.cache_clear()
    monkeypatch.setattr(prompts, "POINTS_SYSTEM", prompts.POINTS_SYSTEM.replace("maximize", "maximise"))
    assert run_path(exp(), "fake", Cell(0.0), 0) != a
    fp._llm_fp.cache_clear()


# ------------------------------------------------------------- checkpoint / resume

def test_resume_after_504_equals_uninterrupted_run(store):
    e, cell = exp(), Cell(0.0)
    path = run_path(e, "fake", cell, 3)
    with pytest.raises(TransientAPIError):
        execute_run(e, cell, 3, llm(DiesAfter(7), e), "fake")
    assert not path.exists() and partial_progress(path) == 7
    execute_run(e, cell, 3, llm(DiesAfter(10_000), e), "fake")
    _, resumed = read_run(path)
    events = [json.loads(x) for x in path.read_text().splitlines() if '"event"' in x]
    assert events and events[0]["after_round"] == 7

    e2 = exp(name="t2", llm={"temperature": 1.0, "max_output_tokens": 512})
    grid.RUNS = store / "runs_clean"
    execute_run(e2, cell, 3, llm(FakeClient(malformed_rate=0), e2), "fake")
    _, clean = read_run(run_path(e2, "fake", cell, 3))
    key = ["round", "slot", "outcome", "points", "notes", "fallback"]
    assert [[r[k] for k in key] for r in resumed] == [[r[k] for k in key] for r in clean]


def test_torn_last_line_is_dropped_and_resumed(store):
    e, cell = exp(), Cell(1.0)
    path = run_path(e, "fake", cell, 1)
    with pytest.raises(TransientAPIError):
        execute_run(e, cell, 1, llm(DiesAfter(5), e), "fake")
    partial = path.with_suffix(".partial")
    partial.write_text(partial.read_text() + '{"type": "round", "round": 6, "sl')   # killed mid-write
    assert partial_progress(path) == 5
    execute_run(e, cell, 1, llm(DiesAfter(10_000), e), "fake")
    assert len(read_run(path)[1]) == e.T


def test_stale_checkpoint_from_other_settings_is_set_aside(store):
    e, cell = exp(), Cell(0.0)
    path = run_path(e, "fake", cell, 2)
    path.parent.mkdir(parents=True)
    path.with_suffix(".partial").write_text(json.dumps({"type": "header", "fingerprint": "other", "seed": 2}) + "\n")
    execute_run(e, cell, 2, llm(FakeClient(malformed_rate=0), e), "fake")
    assert path.exists() and list(path.parent.glob("*.stale-*"))


def test_tampered_checkpoint_fails_replay(store):
    e, cell = exp(), Cell(0.0)
    path = run_path(e, "fake", cell, 4)
    with pytest.raises(TransientAPIError):
        execute_run(e, cell, 4, llm(DiesAfter(6), e), "fake")
    partial = path.with_suffix(".partial")
    lines = partial.read_text().splitlines()
    rec = json.loads(lines[2])
    rec["points"] = 999
    lines[2] = json.dumps(rec)
    partial.write_text("\n".join(lines) + "\n")
    with pytest.raises(ReplayMismatch):
        execute_run(e, cell, 4, llm(FakeClient(malformed_rate=0), e), "fake")


def test_stop_event_pauses_between_rounds(store):
    import threading
    e, cell = exp(), Cell(0.0)
    stop = threading.Event()
    stop.set()
    with pytest.raises(grid.StopRequested):
        execute_run(e, cell, 5, llm(FakeClient(malformed_rate=0), e), "fake", stop=stop)
    assert partial_progress(run_path(e, "fake", cell, 5)) == 1


# ------------------------------------------------------------- seed roles (1.1)

def _cfg(tmp_path, role, seeds, extra=""):
    p = tmp_path / f"{role}.yaml"
    p.write_text(f"name: x\nstage: {role}\nfactors: {{rho: [0.0]}}\nseeds: {seeds}\nmodels: [fake]\n{extra}")
    return p


def test_seed_ranges_enforced(tmp_path):
    assert load_experiment(_cfg(tmp_path, "pilot", "{start: 9001, n: 10}")).seeds[0] == 9001
    with pytest.raises(ValueError):
        load_experiment(_cfg(tmp_path, "pilot", "{start: 0, n: 10}"))
    with pytest.raises(ValueError):
        load_experiment(_cfg(tmp_path, "confirmatory", "{start: 8995, n: 10}"))
    e = load_experiment(_cfg(tmp_path, "confirmatory", "{start: 0, n: 30}",
                             "seeds_by_cell:\n  rho0_fb-outcome_c5_pi0.25: {start: 0, n: 100}\n"))
    assert len(e.seeds_for(e.cells()[0])) == 100
    with pytest.raises(ValueError):
        load_experiment(_cfg(tmp_path, "confirmatory", "{start: 0, n: 3}", "seeds_by_cell:\n  nope: [1]\n"))


def test_shipped_configs_load_with_correct_stages():
    root = Path(__file__).resolve().parent.parent / "configs"
    stages = {p.stem: load_experiment(p).stage for p in root.glob("*.yaml") if not p.stem.startswith("routes")}
    assert stages == {"pilot": "pilot", "confirmatory": "confirmatory", "secondary": "secondary",
                      "full_grid": "full_grid", "smoke": "smoke"}
    conf = load_experiment(root / "confirmatory.yaml")
    from sas.prereg import is_core
    core = [c for c in conf.cells() if is_core(vars(c))]
    assert len(core) == 1 and len(conf.seeds_for(core[0])) == 100


# ------------------------------------------------------------- confirmatory family

def test_confirmatory_verdicts():
    from analyze import confirmatory_family
    base = {"kind": "llm", "rho": 0.0, "feedback": "outcome", "c": 5.0, "pi": 0.25,
            "visibility": "blind", "framing": "points", "tone": "neutral", "n_runs": 100}
    s = pd.DataFrame([
        {**base, "coordinator": "m1", "did": -0.1, "did_lo": -0.15, "did_hi": -0.05, "did_p": 0.0002,
         "did_tost_equivalent": False, "h3_gap": 0.0, "h3_gap_lo": -0.05, "h3_gap_hi": 0.05,
         "h3_p": 0.9, "h3_n_seeds": 100},
        {**base, "coordinator": "m2", "did": 0.0, "did_lo": -0.03, "did_hi": 0.03, "did_p": 0.9,
         "did_tost_equivalent": True, "h3_gap": 0.0, "h3_gap_lo": -0.1, "h3_gap_hi": 0.1,
         "h3_p": 0.95, "h3_n_seeds": 100},
    ])
    fam = confirmatory_family(s, pd.DataFrame()).set_index(["coordinator", "hypothesis"])
    assert fam.loc[("m1", "H1"), "verdict"] == "rejected null"
    assert fam.loc[("m2", "H1"), "verdict"].startswith("equivalent")
    assert fam.loc[("m1", "H3"), "verdict"].startswith("inconclusive")
    assert (fam["p_holm"] >= fam["p"]).all()


# ------------------------------------------------------------- stages, manifest, attempt log (§1)

def test_stage_scoped_reuse_rules(store):
    cell = Cell(0.0)
    conf, sec, pil = exp(stage="confirmatory"), exp(stage="secondary"), exp(stage="pilot")
    execute_run(conf, cell, 0, llm(FakeClient(malformed_rate=0), conf), "fake")
    assert grid.resolve_run(sec, "fake", cell, 0) is not None          # secondary may reuse confirmatory
    execute_run(sec, cell, 1, llm(FakeClient(malformed_rate=0), sec), "fake")
    assert grid.resolve_run(conf, "fake", cell, 1) is None              # confirmatory never reads secondary
    execute_run(pil, cell, 2, llm(FakeClient(malformed_rate=0), pil), "fake")
    for other in (conf, sec, exp(stage="full_grid")):
        assert grid.resolve_run(other, "fake", cell, 2) is None         # nothing reads pilot runs


def test_confirmatory_analysis_refuses_pilot_run(store, tmp_path):
    """Decisions §1.5: a pilot-stage run handed to the confirmatory analysis raises."""
    from build_dataset import load_rounds
    cell = Cell(0.0)
    pil = exp(stage="pilot", seeds=[9001])
    src = execute_run(pil, cell, 9001, llm(FakeClient(malformed_rate=0), pil), "fake")
    conf = exp(stage="confirmatory", seeds=[9001], baselines=[], factors={"rho": [0.0]})
    dst = run_path(conf, "fake", cell, 9001)            # smuggle it into the confirmatory slot
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text())
    with pytest.raises(grid.StageError):
        load_rounds(conf)
    with pytest.raises(grid.StageError):
        grid.check_stages(["confirmatory", "pilot"], "confirmatory")
    grid.check_stages(["confirmatory", "secondary"], "secondary")


def test_manifest_fields_and_attempt_log(store):
    e, cell = exp(), Cell(0.0, feedback="reason")
    path = execute_run(e, cell, 0, llm(FakeClient(malformed_rate=0), e), "fake")
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    h = lines[0]
    for key in ("stage", "task_pool_hash", "templates_hash", "httpx_version", "adaption_version",
                "client", "git_sha", "config_hash", "fingerprint", "started", "schema_version"):
        assert key in h, key
    assert h["stage"] == "secondary" and lines[-1]["event"] == "end"
    assert h["task_pool_hash"] != grid.task_pool_hash(Cell(0.0, pi=0.35), 0, e.T)
    calls = [json.loads(x) for x in path.with_suffix(".calls.jsonl").read_text().splitlines()]
    assert len(calls) == e.T and {c["round"] for c in calls} == set(range(1, e.T + 1))
    assert all(c["request"]["store"] is False and c["response"]["output_text"] for c in calls)


def test_config_without_stage_rejected(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text("name: x\nfactors: {rho: [0.0]}\nseeds: [0]\nmodels: [fake]\n")
    with pytest.raises(ValueError):
        load_experiment(p)


# ------------------------------------------------------------- addendum gates (§4a)

def test_probe_refuses_without_full_recovery(tmp_path, monkeypatch):
    import probe_models
    monkeypatch.setattr(probe_models, "RESULTS", tmp_path)
    assert not probe_models.recovery_passed()[0]
    (tmp_path / "recovery.json").write_text(json.dumps({"studies": 3, "passed": True, "coverage": 1.0}))
    assert not probe_models.recovery_passed()[0]                      # short runs do not count
    (tmp_path / "recovery.json").write_text(json.dumps({"studies": 100, "passed": False,
                                                        "coverage": 0.8, "gate": 0.9}))
    assert not probe_models.recovery_passed()[0]
    (tmp_path / "recovery.json").write_text(json.dumps({"studies": 100, "passed": True,
                                                        "coverage": 0.95, "gate": 0.9}))
    assert probe_models.recovery_passed()[0]


def test_live_run_prints_sanity_block_and_waits_for_confirm(tmp_path):
    import os
    import subprocess
    root = Path(__file__).resolve().parent.parent
    from sas.prompt_approval import approval_hash
    (tmp_path / "approved").write_text(approval_hash())
    env = {**os.environ, "SAS_RESULTS": str(tmp_path), "ADAPTION_API_KEY": "",
           "SAS_APPROVED_FILE": str(tmp_path / "approved")}
    r = subprocess.run([sys.executable, "scripts/run_experiment.py", "--config", "configs/pilot.yaml",
                        "--allow-unprobed"], cwd=root, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    for line in ("stage = pilot", "seeds: 10 (9001-9010)", "pilot design check: OK", "API: openrouter",
                 "qwen3.5-397b -> qwen/qwen3.5-397b-a17b @ alibaba", "temperature = 1.0", "cap 15",
                 "global hard stop: $280.00", "not started"):
        assert line in r.stdout, line
    assert not (tmp_path / "runs").exists()                            # nothing ran, no API call


def test_rendered_prompt_doc_matches_current_prompts():
    """Change 10: compare, never write. Fails after any wording change until
    the doc is re-rendered (scripts/render_prompts.py) and re-approved."""
    from sas.prompt_approval import RENDERED, approval_hash, rendered_doc_hash
    before = RENDERED.read_bytes()
    assert rendered_doc_hash() == approval_hash(), (
        "docs/PROMPTS_RENDERED.md is stale: prompts changed. Run `uv run scripts/render_prompts.py`, "
        "review the doc, and re-approve the new hash.")
    assert RENDERED.read_bytes() == before


def test_approval_hash_sensitive_to_wording_not_to_cells(monkeypatch):
    import sas.prompts as prompts
    from sas.prompt_approval import approval_hash
    h = approval_hash()
    monkeypatch.setattr(prompts, "REASK", prompts.REASK + " ")
    import sas.prompt_approval as pa
    monkeypatch.setattr(pa, "REASK", prompts.REASK)
    assert approval_hash() != h


def test_live_run_refuses_unapproved_prompts(tmp_path, monkeypatch):
    import run_experiment
    import sas.prompt_approval as pa
    monkeypatch.setattr(pa, "APPROVED_FILE", tmp_path / "APPROVED_PROMPT_HASH")
    monkeypatch.setattr(pa, "PREREG", tmp_path / "PREREGISTRATION.md")
    ok, _ = run_experiment.prompts_approved("pilot")
    assert not ok
    (tmp_path / "APPROVED_PROMPT_HASH").write_text(pa.approval_hash() + "\n")
    assert run_experiment.prompts_approved("pilot")[0]
    (tmp_path / "APPROVED_PROMPT_HASH").write_text("0" * 16)
    assert not run_experiment.prompts_approved("confirmatory")[0]
    assert run_experiment.prompts_approved("smoke")[0]                  # smoke is exempt


def test_confirmatory_uses_only_seeds_complete_in_every_cell(store):
    """Addendum 2 §7."""
    from build_dataset import load_rounds
    conf = exp(stage="confirmatory", seeds=[0, 1], baselines=[], factors={"rho": [0.0, 1.0]})
    for cell in conf.cells():
        for seed in (0, 1):
            if (cell.rho, seed) == (1.0, 1):
                continue                                  # seed 1 incomplete at rho = 1
            execute_run(conf, cell, seed, llm(FakeClient(malformed_rate=0), conf), "fake")
    df = load_rounds(conf)
    assert sorted(df["seed"].unique()) == [0]
