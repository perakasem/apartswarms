"""Experiment configs (YAML) -> cells x seeds, and the shared run store.

Run store: results/runs/<coordinator>/<cell_id>/<fingerprint>/seed<NNNN>.jsonl.
Every config is a *view* (cells x seeds x coordinators) over it, so the same
run is never paid for twice. The fingerprint (sas/fingerprint.py) covers
prompts, environment behaviour, T and call settings, so a changed prompt or
temperature can never silently reuse old runs (review fix 1.2). Derived
data, analysis, figures and the credit ledger live in results/<experiment>/.

Checkpointing (robust to HTTP 504s, crashes and Ctrl-C): line 1 of
<seed>.partial is the header; each round is appended and fsynced as soon as it
is played. A rerun replays the stored rounds (verifying each reproduces
exactly) and continues from the first missing round. When all T rounds exist
the file is renamed to .jsonl, and a .jsonl's existence means "complete".

Stages (decisions 2026-11-08, §1.5). Every config has a `stage`, written into
each run header. Runs are stored per stage, and a config may read only:
    pilot         -> pilot
    confirmatory  -> confirmatory
    secondary     -> confirmatory, secondary   (may reuse confirmatory runs)
    full_grid     -> confirmatory, full_grid
    smoke         -> smoke                      (offline fake runs)
Nothing reads pilot runs. The confirmatory analysis additionally refuses any
run whose header stage is not "confirmatory" (check_stages).

Seed ranges (review fix 1.1): pilot configs must use seeds 9000-9999 and every
other config seeds below 9000.

`factors` is either one grid (dict of factor -> levels) or a list of grids
whose union is taken, for one-factor-at-a-time designs. `seeds_by_cell` maps
a cell_id to its own seed spec (e.g. extra seeds in the primary cell).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import yaml

from .env import Cell, Coordinator, run_episode
from .tapes import make_tapes

ROOT = Path(__file__).resolve().parent.parent
# SAS_RESULTS lets tests (or a scratch session) use a separate store.
RESULTS = Path(os.environ.get("SAS_RESULTS", ROOT / "results"))
RUNS = RESULTS / "runs"

STAGES = ("pilot", "confirmatory", "secondary", "full_grid", "smoke")
READS = {"pilot": ("pilot",), "confirmatory": ("confirmatory",),
         "secondary": ("confirmatory", "secondary"), "full_grid": ("confirmatory", "full_grid"),
         "smoke": ("smoke",)}
PILOT_SEEDS = range(9000, 10000)


class StageError(RuntimeError):
    """Runs from a stage this analysis may not use."""


def check_stages(stages, exp_stage: str) -> None:
    """Raise if any run's stage is not readable by an analysis of exp_stage.
    For the confirmatory stage that means: anything but 'confirmatory'."""
    bad = sorted({s for s in stages if s not in READS[exp_stage]})
    if bad:
        raise StageError(f"{exp_stage} analysis refuses runs from stage(s) {bad}")


@dataclass
class Experiment:
    name: str
    T: int = 60
    factors: dict | list = field(default_factory=lambda: {"rho": [0.0, 1.0]})
    payoffs: dict = field(default_factory=lambda: {"v": 10.0, "L": 40.0})
    seeds: list[int] = field(default_factory=lambda: list(range(10)))
    models: list[str] = field(default_factory=list)
    baselines: list[str] = field(default_factory=list)
    llm: dict = field(default_factory=dict)
    stage: str = "smoke"
    seeds_by_cell: dict = field(default_factory=dict)
    disabled: str = ""      # non-empty: live runs refused, with this reason
    source: str = ""

    @property
    def role(self) -> str:
        """confirmatory | pilot | exploratory (secondary, full_grid, smoke)."""
        return self.stage if self.stage in ("pilot", "confirmatory") else "exploratory"

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(Path(self.source).read_bytes()).hexdigest()[:12] if self.source else ""

    FACTORS = ("rho", "feedback", "c", "pi", "visibility", "framing", "tone")

    def cells(self) -> list[Cell]:
        grids = self.factors if isinstance(self.factors, list) else [self.factors]
        out: dict[str, Cell] = {}
        for grid in grids:
            unknown = set(grid) - set(self.FACTORS)
            if unknown:
                raise ValueError(f"unknown factor(s) {sorted(unknown)}; allowed {self.FACTORS}")
            f = {"rho": [0.0], "feedback": ["outcome"], "c": [5.0], "pi": [0.25],
                 "visibility": ["blind"], "framing": ["points"], "tone": ["neutral"], **grid}
            for r, fb, c, p, vis, fr, tn in itertools.product(*(f[k] for k in self.FACTORS)):
                cell = Cell(rho=float(r), feedback=fb, c=float(c), pi=float(p),
                            v=float(self.payoffs.get("v", 10)), L=float(self.payoffs.get("L", 40)),
                            visibility=vis, framing=fr, tone=tn)
                out.setdefault(cell.cell_id, cell)
        return list(out.values())

    def seeds_for(self, cell: Cell) -> list[int]:
        return self.seeds_by_cell.get(cell.cell_id, self.seeds)

    def all_seeds(self) -> list[int]:
        out = set(self.seeds)
        for v in self.seeds_by_cell.values():
            out |= set(v)
        return sorted(out)

    def llm_settings(self) -> dict:
        return {"api": "openrouter", "max_output_tokens": 512, "temperature": None,
                "require_no_reasoning": True, "max_reasks": 2, "rps": 4, "max_inflight": 4,
                "concurrency": 4, "max_credits": 10, "max_retries": 5, "global_max_usd": 140.0,
                "routes": "configs/routes_openrouter.yaml", "max_inflight_by_model": {},
                "inflight_floor": None, **self.llm}

    def routes(self) -> dict:
        """OpenRouter model label -> {slug, provider, reasoning, price_in, price_out}."""
        return yaml.safe_load((ROOT / self.llm_settings()["routes"]).read_text())

    def api_host(self) -> str:
        from .openrouter import API_BASE
        return API_BASE

    def coordinators(self) -> list[str]:
        return list(self.models) + ["baseline-" + b.replace(":", "") for b in self.baselines]

    def out_dir(self) -> Path:
        return RESULTS / self.name


def _seed_list(spec) -> list[int]:
    if isinstance(spec, dict):
        start = int(spec.get("start", 0))
        return list(range(start, start + int(spec["n"])))
    return [int(s) for s in spec]


def load_experiment(path: str | Path) -> Experiment:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    seeds = raw.pop("seeds", None)
    by_cell = {k: _seed_list(v) for k, v in (raw.pop("seeds_by_cell", None) or {}).items()}
    exp = Experiment(**raw, seeds_by_cell=by_cell, source=str(path))
    if seeds is not None:
        exp.seeds = _seed_list(seeds)
    if "stage" not in raw:
        raise ValueError(f"{path}: every config needs a `stage` ({', '.join(STAGES)})")
    if exp.stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}")
    if exp.llm_settings()["api"] != "openrouter":
        raise ValueError(f"{path}: llm.api must be openrouter (the only supported client)")
    unknown = set(by_cell) - {c.cell_id for c in exp.cells()}
    if unknown:
        raise ValueError(f"seeds_by_cell names cells not in this design: {sorted(unknown)}")
    in_pilot = [s for s in exp.all_seeds() if s in PILOT_SEEDS]
    if exp.role == "pilot" and len(in_pilot) != len(exp.all_seeds()):
        raise ValueError("pilot configs must use seeds 9000-9999 only")
    if exp.role != "pilot" and in_pilot:
        raise ValueError("seeds 9000-9999 are reserved for pilots (review fix 1.1)")
    return exp


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def fingerprint_for(exp: Experiment, coordinator: str, cell: Cell) -> str:
    from .fingerprint import baseline_fingerprint, llm_fingerprint
    if coordinator.startswith("baseline-"):
        spec = next(b for b in exp.baselines if "baseline-" + b.replace(":", "") == coordinator)
        return baseline_fingerprint(cell, exp.T, spec)
    # API host and pinned route (never the key) are part of the cache key: two
    # providers for one model never reuse each other's runs.
    route = exp.routes().get(coordinator, {})
    return llm_fingerprint(cell, exp.T, coordinator, exp.llm_settings(),
                           api_host=exp.api_host(), route=route)


def run_path(exp: Experiment, coordinator: str, cell: Cell, seed: int,
             stage: str | None = None) -> Path:
    """Where this config writes the run (its own stage directory)."""
    fp = fingerprint_for(exp, coordinator, cell)
    return RUNS / coordinator / cell.cell_id / fp / (stage or exp.stage) / f"seed{seed:04d}.jsonl"


def resolve_run(exp: Experiment, coordinator: str, cell: Cell, seed: int) -> Path | None:
    """A completed run this config may use, from any stage it can read; else None."""
    for st in READS[exp.stage]:
        p = run_path(exp, coordinator, cell, seed, stage=st)
        if p.exists():
            return p
    return None


def task_pool_hash(cell: Cell, seed: int, T: int) -> str:
    from .tasks import make_task
    tp = make_tapes(seed, T)
    pool = [make_task(seed, t, tp.kind(t), tp.theta(t, cell.pi)).to_dict() for t in range(T)]
    return hashlib.sha256(json.dumps(pool, sort_keys=True).encode()).hexdigest()[:12]


def templates_hash() -> str:
    """Stand-in for the PRD's bank hash: every text a worker can emit."""
    from . import tasks
    parts = [tasks.PERMISSION_OBJECTION, tasks.EVIDENCE_OBJECTION, tasks.COMPLETION,
             tasks.PREACHY_PREFIX, tasks.PREACHY_SUFFIX]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:12]


def client_versions() -> dict:
    """Raw HTTPS via httpx (no provider SDK); record what is used."""
    import importlib.metadata as md
    out = {"client": "sas.openrouter (httpx)"}
    for pkg in ("httpx",):
        try:
            out[f"{pkg}_version"] = md.version(pkg)
        except md.PackageNotFoundError:
            out[f"{pkg}_version"] = None
    return out


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


class StopRequested(RuntimeError):
    """Raised between rounds when the runner asks in-flight runs to stop."""


def _read_lines(path: Path) -> list[dict]:
    """Parse JSONL, stopping at a torn final line (process killed mid-write)."""
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            break
    return out


def _write_line(f, obj, durable: bool = True):
    f.write(json.dumps(obj, default=_jsonable) + "\n")
    f.flush()
    if durable:
        os.fsync(f.fileno())


def execute_run(exp: Experiment, cell: Cell, seed: int, coord: Coordinator,
                coordinator_name: str, extra: dict | None = None,
                stop: threading.Event | None = None, durable: bool = True) -> Path:
    """Play (or resume) one run and return the completed file's path.

    durable=False skips the per-round fsync (free, instant baselines).
    Coordinators that call an API get a per-run attempt log next to the run
    file (<seed>.calls.jsonl, append-only: every attempt, retry and re-ask)."""
    done = resolve_run(exp, coordinator_name, cell, seed)
    if done is not None:
        return done
    path = run_path(exp, coordinator_name, cell, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    if hasattr(coord, "set_attempt_log"):
        coord.set_attempt_log(path.with_suffix(".calls.jsonl"))
    tapes = make_tapes(seed, exp.T)
    header = {"type": "header", "schema_version": 2, "experiment": exp.name, "stage": exp.stage,
              "coordinator": coordinator_name, "cell": asdict(cell), "cell_id": cell.cell_id,
              "seed": seed, "T": exp.T, "fingerprint": path.parent.parent.name,
              "labels": list(tapes.labels), "config_hash": exp.config_hash, "git_sha": git_sha(),
              "task_pool_hash": task_pool_hash(cell, seed, exp.T), "templates_hash": templates_hash(),
              **client_versions(), "started": time.time(), **(extra or {})}

    prior: list[dict] = []
    events: list[dict] = []
    if partial.exists():
        lines = _read_lines(partial)
        old = lines[0] if lines and lines[0].get("type") == "header" else None
        if (old and old.get("fingerprint") == header["fingerprint"] and old.get("seed") == seed
                and old.get("stage") == exp.stage):
            header = old                       # keep the original header (start time, sha)
            prior = [x for x in lines[1:] if x.get("type") == "round"]
            events = [x for x in lines[1:] if x.get("type") == "event"]
        else:
            partial.rename(partial.with_name(partial.name + f".stale-{int(time.time())}"))
    # Rewrite cleanly (drops any torn line), then append as rounds complete.
    with open(partial, "w") as f:
        _write_line(f, header, durable)
        for e in events:
            _write_line(f, e, durable)
        if prior:
            _write_line(f, {"type": "event", "event": "resume", "after_round": len(prior),
                            "time": time.time(), "git_sha": git_sha()}, durable)
        for rec in prior:
            _write_line(f, rec, durable)

    with open(partial, "a") as f:
        def on_round(rec):
            _write_line(f, {"type": "round", **rec}, durable)
            if stop is not None and stop.is_set() and rec["round"] < exp.T:
                raise StopRequested(f"stopped after round {rec['round']}")

        run_episode(cell, tapes, coord, exp.T, prior=prior, on_round=on_round)
        _write_line(f, {"type": "event", "event": "end", "time": time.time()}, durable)
    partial.replace(path)
    return path


def partial_progress(path: Path) -> int:
    """Rounds already checkpointed for an unfinished run (0 if none)."""
    partial = path.with_suffix(".partial")
    if not partial.exists():
        return 0
    return sum(1 for x in _read_lines(partial) if x.get("type") == "round")


def read_run(path: Path) -> tuple[dict, list[dict]]:
    lines = _read_lines(path)
    return lines[0], [x for x in lines[1:] if x.get("type") == "round"]
