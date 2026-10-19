"""Pooled paired comparison for the turn-capped hard set. Usage: python bench/turncap_mcnemar.py bench/turncap3.jsonl"""
import json, sys
from math import comb
rows = [json.loads(l) for l in open(sys.argv[1])]
cell = {}
for r in rows:
    cell[(r['task'], r['arm'], r['run'])] = r
arms = sorted({k[1] for k in cell})
print("rows", len(rows), "unique cells", len(cell), "errors", sum(1 for r in cell.values() if r['is_error']))
for a in arms:
    c = [v for k, v in cell.items() if k[1] == a]
    print(f"{a}: pass {sum(v['passed'] for v in c)}/{len(c)}  mean tokens_in+out {sum(v['tokens_in']+v['tokens_out'] for v in c)/len(c):.0f}")
def mcn(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)
base = 'baseline'
for a in arms:
    if a == base: continue
    b = c = 0
    for (t, arm, run), v in cell.items():
        if arm != a or (t, base, run) not in cell: continue
        x, y = cell[(t, base, run)]['passed'], v['passed']
        b += x and not y; c += y and not x
    print(f"{base} vs {a}: base-only {b}, arm-only {c}, exact p={mcn(b, c):.3f}")
