#!/usr/bin/env python3
"""Red-team: fabrications written to evade the current detectors. Expected to fail some.
Run: uv run python forensics/redteam.py   (prints caught k/n per case; seeds 1-20)."""
import math, os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from forensics import bench


def benford_forged(seed):
    """Digits sampled to follow Benford exactly, last digits uniform, no round bias: a careful faker."""
    r = random.Random(seed)
    rows = ["firm,revenue_usd,employees"]
    for i in range(150):
        rows.append("firm%d,%d,%d" % (i, int(10 ** r.uniform(3, 7)), int(10 ** r.uniform(1, 3.5))))
    return "forged_benford.csv", "\n".join(rows) + "\n"


def llm_plausible_table(seed):
    """What an LLM types: mid-size revenue figures, varied but human-looking, 60 rows."""
    r = random.Random(seed)
    rows = ["firm,revenue_2019_usd,growth_pct"]
    for i in range(60):
        rows.append("Firm %d,%d,%.1f" % (i, r.randint(180, 950) * 1000 + r.randint(0, 999), r.uniform(-8, 22)))
    return "llm_plausible.csv", "\n".join(rows) + "\n"


def narrow_range_md(seed):
    r = random.Random(seed)
    rows = ["| model | acc | f1 |", "|---|---|---|"]
    for i in range(40):
        rows.append("| m%d | %.3f | %.3f |" % (i, r.uniform(0.82, 0.91), r.uniform(0.80, 0.90)))
    return "narrow.md", "\n".join(rows) + "\n"


def smooth_trend(seed):
    r = random.Random(seed)
    rows = ["year,sales,cost"]
    s, c = 1200.0, 800.0
    for y in range(2000, 2060):
        s *= 1.05 + r.uniform(-0.003, 0.003); c *= 1.04 + r.uniform(-0.003, 0.003)
        rows.append("%d,%.1f,%.1f" % (y, s, c))
    return "smooth.csv", "\n".join(rows) + "\n"


def json_plausible(seed):
    """JSON results array with varied 3-digit counts and 2-decimal rates; no round bias."""
    import json
    r = random.Random(seed)
    rows = [{"site": "s%d" % i, "n": r.randint(120, 980), "rate": round(r.uniform(2.0, 9.0), 2)} for i in range(50)]
    return "results.json", json.dumps(rows)


def grim_valid_means(seed):
    """Means reported with n that are GRIM-consistent (derived from integer sums): a faker who checks."""
    r = random.Random(seed)
    rows = ["group,n,mean_score"]
    for i in range(40):
        n = r.randint(12, 60)
        rows.append("g%d,%d,%.2f" % (i, n, round(r.randint(n * 20, n * 80) / n, 2)))
    return "grim_ok.csv", "\n".join(rows) + "\n"


CASES = [benford_forged, llm_plausible_table, narrow_range_md, smooth_trend, json_plausible, grim_valid_means]


def main():
    for fn in CASES:
        k = 0
        for s in range(1, 21):
            name, text = fn(s)
            k += bool(bench.run_text(name, text)["tripped"])
        print("%s caught %d/20" % (fn.__name__, k))


def provenance_main():
    """Same fabrications through the provenance check with a transcript that never showed the numbers."""
    import json, tempfile
    from forensics import hook
    d = tempfile.mkdtemp()
    tp = os.path.join(d, "t.jsonl")
    with open(tp, "w") as f:
        f.write(json.dumps({"message": {"role": "user", "content": "make the table"}}) + "\n")
    for fn in CASES:
        k = 0
        for s in range(1, 21):
            name, text = fn(s)
            p = os.path.join(d, name)
            with open(p, "w") as f:
                f.write(text)
            k += bool(hook.provenance_finding(p, tp))
        print("provenance %s caught %d/20" % (fn.__name__, k))


if __name__ == "__main__":
    main()
    provenance_main()
