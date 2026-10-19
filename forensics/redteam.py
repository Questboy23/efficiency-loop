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


CASES = [benford_forged, llm_plausible_table, narrow_range_md, smooth_trend]


def main():
    for fn in CASES:
        k = 0
        for s in range(1, 21):
            name, text = fn(s)
            k += bool(bench.run_text(name, text)["tripped"])
        print("%s caught %d/20" % (fn.__name__, k))


if __name__ == "__main__":
    main()
