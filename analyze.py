#!/usr/bin/env python3
"""Compare each arm against the baseline with paired statistics.

  python3 analyze.py results.jsonl

Pass rate: exact McNemar test on (task, run) pairs that disagree.
Cost and turns: paired sign-flip permutation test on per-task means.
Cost per resolved task: bootstrap 95% interval over tasks.
p-values are Holm-corrected across all comparisons (stricter when you test more things).
"""
import json, math, random, sys
from collections import defaultdict
from statistics import mean, median

B_BOOT, B_PERM = 5000, 20000


def load(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    return [r for r in rows if "error" not in r and r.get("cost_usd") is not None]


def exact_mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def perm_test(diffs, rng):
    obs = abs(mean(diffs))
    hits = 0
    for _ in range(B_PERM):
        s = mean(d if rng.random() < 0.5 else -d for d in diffs)
        if abs(s) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (B_PERM + 1)


def cost_per_resolved(rows):
    solved = sum(r["passed"] for r in rows)
    return sum(r["cost_usd"] for r in rows) / solved if solved else float("inf")


def bootstrap_interval(bx, by, task_names, rng):
    """Bootstrap cost-per-resolved ratio. Returns (point_pct, lo_pct, hi_pct) or None if unsolvable."""
    bx_solved = sum(r["passed"] for r in bx)
    by_solved = sum(r["passed"] for r in by)
    if bx_solved == 0 or by_solved == 0:
        return None
    cx = cost_per_resolved(bx)
    cy = cost_per_resolved(by)
    point = cy / cx - 1
    boots = []
    for _ in range(B_BOOT):
        pick = [rng.choice(task_names) for _ in task_names]
        sx = [r for t in pick for r in bx if r["task"] == t]
        sy = [r for t in pick for r in by if r["task"] == t]
        if sum(r["passed"] for r in sx) == 0 or sum(r["passed"] for r in sy) == 0:
            continue
        cxx, cyy = cost_per_resolved(sx), cost_per_resolved(sy)
        if math.isfinite(cxx) and math.isfinite(cyy) and cxx > 0:
            boots.append(cyy / cxx - 1)
    if len(boots) < 10:
        return None
    boots.sort()
    lo = boots[int(0.025 * len(boots))]
    hi = boots[int(0.975 * len(boots)) - 1]
    return point, lo, hi


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, running = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = running
    return adj


def main(path):
    rng = random.Random(0)
    rows = load(path)
    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    if "baseline" not in by_arm:
        sys.exit("need a baseline arm")

    print(f"{'arm':16s} {'runs':>5s} {'pass%':>7s} {'mean $':>8s} {'median $':>9s} {'$/resolved':>11s} {'turns':>6s}")
    for arm, rs in by_arm.items():
        print(f"{arm:16s} {len(rs):5d} {100*mean(r['passed'] for r in rs):6.1f}% "
              f"{mean(r['cost_usd'] for r in rs):8.4f} {median(r['cost_usd'] for r in rs):9.4f} "
              f"{cost_per_resolved(rs):11.4f} {mean((r.get('num_turns') or 0) for r in rs):6.1f}")

    base_idx = {(r["task"], r["run"]): r for r in by_arm["baseline"]}
    tests, labels, effects = [], [], []
    for arm, rs in by_arm.items():
        if arm == "baseline":
            continue
        pairs = [(base_idx[(r["task"], r["run"])], r) for r in rs if (r["task"], r["run"]) in base_idx]
        if not pairs:
            continue
        b = sum(1 for x, y in pairs if x["passed"] and not y["passed"])
        c = sum(1 for x, y in pairs if y["passed"] and not x["passed"])
        tests.append(exact_mcnemar(b, c)); labels.append(f"{arm}: pass rate (fixed {c}, broke {b})")
        effects.append(f"{100*(mean(y['passed'] for _, y in pairs) - mean(x['passed'] for x, _ in pairs)):+.1f} pts")

        per_task = defaultdict(lambda: [[], []])
        for x, y in pairs:
            per_task[x["task"]][0].append(x["cost_usd"]); per_task[x["task"]][1].append(y["cost_usd"])
        diffs = [mean(v[1]) - mean(v[0]) for v in per_task.values()]
        base_mean = mean(mean(v[0]) for v in per_task.values())
        tests.append(perm_test(diffs, rng)); labels.append(f"{arm}: cost per run")
        effects.append(f"{100*mean(diffs)/base_mean:+.1f}%")

        task_names = list(per_task)
        bx = [x for x, _ in pairs]; by = [y for _, y in pairs]
        bi = bootstrap_interval(bx, by, task_names, rng)
        if bi is not None:
            point, lo, hi = bi
            print(f"\n{arm}: cost per resolved task {100*point:+.1f}% vs baseline "
                  f"(95% interval {100*lo:+.1f}% to {100*hi:+.1f}%)")
        else:
            print(f"\n{arm}: cost per resolved task — insufficient solves in one or both arms for bootstrap")

    if tests:
        print("\nPaired tests vs baseline (Holm-corrected):")
        for lab, eff, p, padj in zip(labels, effects, tests, holm(tests)):
            verdict = "SIGNIFICANT" if padj < 0.05 else "not significant"
            print(f"  {lab:48s} effect {eff:>9s}  p={p:.4f}  adjusted p={padj:.4f}  {verdict}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results.jsonl")
