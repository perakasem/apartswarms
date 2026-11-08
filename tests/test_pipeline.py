"""End to end through the real scripts, offline, in an isolated results root:
config -> runs (fake LLM, incl. a simulated 504 outage) -> dataset -> analysis
-> figures -> report, for exploratory, pilot and confirmatory roles."""

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    return tmp_path_factory.mktemp("results")


def run(results, *args, ok=(0,)):
    env = {**os.environ, "SAS_RESULTS": str(results)}
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode in ok, r.stdout + r.stderr
    return r


def config(results, name, body):
    p = results / f"{name}.yaml"
    p.write_text(f"name: {name}\nT: 30\n" + body)
    return str(p)


def analyse(results, cfg):
    run(results, "scripts/build_dataset.py", "--config", cfg)
    a = run(results, "scripts/analyze.py", "--config", cfg, "--B", "200").stdout
    assert "replay audit: 0 mismatches" in a
    run(results, "scripts/figures.py", "--config", cfg)
    run(results, "scripts/report.py", "--config", cfg)
    return a


def test_exploratory_with_504_outage_resumes_to_completion(results):
    cfg = config(results, "explore", """stage: full_grid
factors: {rho: [0.0, 0.5, 1.0]}
seeds: {start: 0, n: 3}
models: [fake-flaky]
baselines: [bayes, bayes_known, uniform]
""")
    codes = []
    for _ in range(12):   # each invocation: 504 storm after 25 calls -> breaker -> exit 2
        r = run(results, "scripts/run_experiment.py", "--config", cfg, ok=(0, 2))
        codes.append(r.returncode)
        if r.returncode == 0:
            break
    assert codes[0] == 2 and codes[-1] == 0, codes
    assert "0 to run" in run(results, "scripts/run_experiment.py", "--config", cfg).stdout
    run(results, "scripts/run_baselines.py", "--config", cfg)
    assert not list((results / "runs").rglob("*.partial"))
    analyse(results, cfg)
    out = results / "explore"
    s = pd.read_csv(out / "analysis" / "summary.csv")
    assert set(s["coordinator"]) == {"fake-flaky", "baseline-bayes", "baseline-bayes_known", "baseline-uniform"}
    assert s["did"].notna().all() and s.loc[s.kind == "llm", "h3known_gap"].notna().all()
    h2 = pd.read_csv(out / "analysis" / "h2.csv")
    assert set(h2["h2_rhos"]) == {"0,0.5,1"} and h2["h2_contrast"].notna().all()
    assert not (out / "analysis" / "confirmatory.csv").exists()     # exploratory: no family
    rep = (out / "REPORT.md").read_text()
    assert rep.count("### fake-flaky") == 3 and "ρ-known upper bound" in rep
    assert rep.startswith("**EXPLORATORY — not confirmatory**") and "## Pilot gate" not in rep
    assert len(list((out / "figures").glob("*.pdf"))) >= 6


def test_pilot_full_report_with_gate(results):
    cfg = config(results, "pilot_t", """stage: pilot
factors: {rho: [0.0, 1.0]}
seeds: {start: 9001, n: 4}
models: [fake]
baselines: [bayes, bayes_known]
""")
    run(results, "scripts/run_experiment.py", "--config", cfg)
    run(results, "scripts/run_baselines.py", "--config", cfg)
    analyse(results, cfg)
    out = results / "pilot_t"
    s = pd.read_csv(out / "analysis" / "summary.csv")
    assert {"did", "lambda", "h3_gap", "share_complier", "manip_pass"} <= set(s.columns)   # §2.3: unmasked
    rep = (out / "REPORT.md").read_text()
    assert rep.startswith("**EXPLORATORY — not confirmatory**")
    gate = rep[rep.index("## Pilot gate"):]
    for line in ("positive control", "placebo (ρ=0)", "manipulation check (ρ=1)", "fallback rate",
                 "informational: 10 seeds cannot resolve direction"):
        assert line in gate, line
    assert "Reply length after API retries" in rep and "Manipulation check (ρ>0)" in rep
    assert "## Reply format and awareness" in rep and "descriptive, not causal" in rep
    assert {"preamble_rate", "eval_aware_rate", "game_frame_rate"} <= set(s.columns)
    assert (out / "analysis" / "preamble_types.csv").exists()
    assert (out / "data" / "awareness_hits.csv").exists()


def test_confirmatory_family(results):
    cfg = config(results, "conf_t", """stage: confirmatory
factors: {rho: [0.0, 0.5, 1.0]}
seeds: {start: 0, n: 4}
seeds_by_cell:
  rho0_fb-outcome_c5_pi0.25: {start: 0, n: 6}
models: [fake]
baselines: [bayes, bayes_known]
""")
    run(results, "scripts/run_experiment.py", "--config", cfg)
    run(results, "scripts/run_baselines.py", "--config", cfg)
    analyse(results, cfg)
    fam = pd.read_csv(results / "conf_t" / "analysis" / "confirmatory.csv")
    assert set(fam["hypothesis"]) == {"H1", "H2", "H3"}
    assert (fam["p_holm"] >= fam["p"]).all() and fam["verdict"].notna().all()
    s = pd.read_csv(results / "conf_t" / "analysis" / "summary.csv")
    core = s[(s.coordinator == "fake") & (s.rho == 0)]
    assert int(core["n_runs"].iat[0]) == 6
    rep = (results / "conf_t" / "REPORT.md").read_text()
    assert "Confirmatory family" in rep and "EXPLORATORY" not in rep
    h2 = fam[fam["hypothesis"] == "H2"].iloc[0]
    assert "root" in fam.columns and h2["rho_star"] == 0.375        # §2.5: slope test + root
    assert "## H2: fitted switch point (primary)" in rep
