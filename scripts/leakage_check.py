"""Blind-assignment leakage test (review 2.9, checklist item 6).

Offline (always): over many generated tasks,
  1. a naive-Bayes classifier on title tokens, trained/tested on disjoint
     halves, must not beat the majority-class rate (binomial test), and
  2. the objection text must be identical whether the objection is correct
     or not (so wording cannot reveal correctness without the task fact), and
  3. the task fact must determine theta (so the reason-visible condition
     really is verifiable).
Optional (--model): ask an LLM to guess theta from titles alone.

  uv run scripts/leakage_check.py [--n 20000] [--model qwen3.5-397b --llm-n 60]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.grid import RESULTS  # noqa: E402
from sas.tasks import make_task  # noqa: E402

TOK = re.compile(r"[A-Za-z0-9.]+")


def tasks(n: int, pi: float = 0.25):
    rng = np.random.default_rng(1)
    out = []
    for i in range(n):
        theta = "O" if rng.random() < pi else "P"
        kind = "permission" if rng.random() < 0.5 else "evidence"
        out.append(make_task(900_000 + i, 0, kind, theta))
    return out


def naive_bayes_accuracy(train, test) -> tuple[float, float]:
    counts = {"O": Counter(), "P": Counter()}
    prior = Counter(t.theta for t in train)
    for t in train:
        counts[t.theta].update(set(TOK.findall(t.title.lower())))
    vocab = set(counts["O"]) | set(counts["P"])
    correct = 0
    for t in test:
        toks = set(TOK.findall(t.title.lower()))
        score = {}
        for th in ("O", "P"):
            score[th] = np.log(prior[th]) + sum(
                np.log((counts[th][w] + 1) / (prior[th] + 2)) for w in toks if w in vocab)
        correct += max(score, key=score.get) == t.theta
    majority = max(prior.values()) / sum(prior.values())
    return correct / len(test), majority


def fact_determines_theta(t) -> bool:
    if t.kind == "permission":
        req = re.search(r"Required permission: (\S+)\.", t.fact).group(1)
        granted = re.search(r"Granted permissions: (.+)\.", t.fact).group(1).split(", ")
        return (req in granted) == (t.theta == "P")
    m = re.search(r"measured value = ([\d.]+)\. Requested conclusion: (.+)\.", t.fact)
    value, concl = float(m.group(1)), m.group(2)
    thr = float(re.search(r"(\d+)(%| tickets)", concl).group(1))
    above = any(w in concl for w in ("above", "more than", "exceeded"))
    supported = value > thr if above else value < thr
    return supported == (t.theta == "P")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--model")
    ap.add_argument("--llm-n", type=int, default=60)
    args = ap.parse_args()
    ts = tasks(args.n)
    half = len(ts) // 2
    acc, maj = naive_bayes_accuracy(ts[:half], ts[half:])
    n_test = len(ts) - half
    p = binomtest(round(acc * n_test), n_test, maj, alternative="greater").pvalue
    print(f"[title->theta] naive Bayes held-out accuracy {acc:.4f} vs majority {maj:.4f} "
          f"(one-sided p = {p:.3f})  {'OK' if p > 0.01 else 'LEAK'}")

    by_kind = {}
    for t in ts:
        by_kind.setdefault((t.kind, t.objection.split(":")[0]), set()).add(t.theta)
    # identical template across theta: the objection is a function of the
    # required item only, never of theta
    same = all(
        make_task(900_000 + i, 0, t.kind, "O").objection == make_task(900_000 + i, 0, t.kind, "P").objection
        and make_task(900_000 + i, 0, t.kind, "O").title == make_task(900_000 + i, 0, t.kind, "P").title
        for i, t in enumerate(ts[:2000]))
    print(f"[objection/title identical across theta for the same task] {'OK' if same else 'LEAK'}")
    det = all(fact_determines_theta(t) for t in ts)
    print(f"[task fact determines theta] {'OK' if det else 'BROKEN'}")
    result = {"nb_accuracy": acc, "majority": maj, "p": p, "identical_across_theta": same,
              "fact_determines_theta": det}

    if args.model:
        import yaml
        from sas.grid import ROOT
        from sas.openrouter import KeyPool, OpenRouterClient, load_keys
        routes = yaml.safe_load((ROOT / "configs/routes_openrouter.yaml").read_text())
        client = OpenRouterClient(routes=routes, pool=KeyPool(load_keys()), max_usd=0.5, global_max_usd=280.0,
                                  ledger_path=None, global_ledger_path=RESULTS / "openrouter_ledger.jsonl")
        sample = ts[: args.llm_n]
        hits = 0
        for t in sample:
            r = client.respond(model=args.model, max_output_tokens=16, input=(
                f'Task title: "{t.title}"\nWill doing this task as stated be a problem '
                "(for example missing permissions or unsupported conclusions)? Answer only YES or NO."),
                instructions="Answer with one word.")
            guess = "O" if "YES" in r["text"].upper() else "P"
            hits += guess == t.theta
        base = max(sum(t.theta == "O" for t in sample), sum(t.theta == "P" for t in sample)) / len(sample)
        p_llm = binomtest(hits, len(sample), base, alternative="greater").pvalue
        print(f"[LLM title probe] {args.model}: {hits}/{len(sample)} vs majority {base:.2f} (p = {p_llm:.3f})")
        result.update(llm_model=args.model, llm_hits=hits, llm_n=len(sample), llm_p=p_llm)

    out = RESULTS / "leakage_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    ok = p > 0.01 and same and det
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
