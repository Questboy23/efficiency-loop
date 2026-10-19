"""Seeded generators for real-shaped and fabricated-shaped test data."""
import json
import math
import random


def lognormal_csv(seed, n=400, sigma=2.0):
    r = random.Random(seed)
    rows = ["id,amount,qty,rate"]
    for i in range(n):
        rows.append("%d,%.2f,%d,%.4f" % (i, math.exp(r.gauss(6, sigma)), r.randint(1, 500), r.lognormvariate(0, 1.5)))
    return "\n".join(rows) + "\n"


def pareto_csv(seed, n=400, alpha=1.2):
    r = random.Random(seed)
    rows = ["firm,revenue,employees"]
    for i in range(n):
        rows.append("f%d,%.1f,%d" % (i, 1000 * r.paretovariate(alpha), int(20 * r.paretovariate(alpha))))
    return "\n".join(rows) + "\n"


def stats_table_md(seed, n=30):
    r = random.Random(seed)
    lines = ["| group | n | mean score | sd | p |", "|---|---|---|---|---|"]
    for i in range(n):
        k = r.randint(12, 60)
        data = [r.randint(1, 7) for _ in range(k)]
        m = sum(data) / k
        sd = (sum((x - m) ** 2 for x in data) / (k - 1)) ** 0.5
        lines.append("| g%d | %d | %.2f | %.2f | %.3f |" % (i, k, m, sd, r.random()))
    return "\n".join(lines) + "\n"


def total_table_csv(seed, n=12):
    r = random.Random(seed)
    rows = ["region,q1,q2,q3,total"]
    sums = [0, 0, 0, 0]
    for i in range(n):
        v = [r.randint(1000, 90000) for _ in range(3)]
        rows.append("r%d,%d,%d,%d,%d" % (i, *v, sum(v)))
        for k in range(3):
            sums[k] += v[k]
        sums[3] += sum(v)
    rows.append("Total,%d,%d,%d,%d" % tuple(sums))
    return "\n".join(rows) + "\n"


# ---- fabricated shapes: each returns (filename, text, expected_test_prefix)
def fab_uniform_digits(seed):
    r = random.Random(seed)
    rows = ["firm,revenue_usd,cost_usd"]
    for i in range(300):
        rows.append("f%d,%d%s,%d%s" % (i, r.randint(1, 9), "".join(r.choice("0123456789") for _ in range(r.randint(1, 5))), r.randint(1, 9), "".join(r.choice("0123456789") for _ in range(r.randint(1, 4)))))
    # last digit preference as a human types: 7 and 3 over-represented
    rows = [rows[0]] + [x[:-1] + r.choice("3777") if k % 2 else x for k, x in enumerate(rows[1:])]
    return "uniform_digits.csv", "\n".join(rows) + "\n", ("benford", "last")


def fab_round(seed):
    r = random.Random(seed)
    rows = ["firm,revenue_usd"] + ["f%d,%d" % (i, r.choice([5, 10, 20, 25, 50, 100, 150, 200, 250, 500, 750, 1000, 1500, 2500]) * r.choice([1, 10, 100])) for i in range(80)]
    return "round_heavy.csv", "\n".join(rows) + "\n", ("round",)


def fab_grim(seed):
    r = random.Random(seed)
    rows = ["group,n,mean_score,min_score,max_score"]
    for i in range(25):
        n = r.randint(8, 24)
        rows.append("g%d,%d,%.2f,1,7" % (i, n, r.uniform(2, 6)))
    return "grim.csv", "\n".join(rows) + "\n", ("grim",)


def fab_duplicates(seed):
    r = random.Random(seed)
    base = ["f%d,%d,%d,%d,%d" % (i, r.randint(1000, 99999), r.randint(1000, 99999), r.randint(1000, 99999), r.randint(100, 999)) for i in range(15)]
    rows = ["firm,a,b,c,d"] + base + [x.replace("f", "g", 1) for x in base[:10]]
    return "dup_rows.csv", "\n".join(rows) + "\n", ("duplicate",)


def fab_impossible(seed):
    r = random.Random(seed)
    rows = ["id,p_value,share_%,sd,n"]
    for i in range(20):
        rows.append("%d,%.3f,%.1f,%.2f,%d" % (i, r.random() if i % 5 else 1.0 + r.random(), r.uniform(5, 60), r.uniform(0.5, 3), r.randint(10, 90)))
    return "impossible.csv", "\n".join(rows) + "\n", ("impossible", "negative")


def fab_impossible_pct(seed):
    r = random.Random(seed)
    rows = ["id,score_%,sd,n"]
    for i in range(20):
        rows.append("%d,%.1f,%.2f,%d" % (i, r.uniform(20, 99) if i % 6 else 130 + i, -r.uniform(0.5, 3) if i == 3 else r.uniform(0.5, 3), r.randint(10, 90)))
    return "impossible_pct.csv", "\n".join(rows) + "\n", ("impossible", "negative")


def fab_total(seed):
    t = total_table_csv(seed).split("\n")
    last = t[-2].split(",")
    last[2] = str(int(last[2]) + 4000)
    t[-2] = ",".join(last)
    return "bad_total.csv", "\n".join(t), ("total",)


def fab_step(seed):
    r = random.Random(seed)
    rows = ["month,sales_usd,visits"] + ["%d,%d,%d" % (i, 1000 + 250 * i, r.randint(100, 900)) for i in range(1, 41)]
    return "step.csv", "\n".join(rows) + "\n", ("constant_step",)


def fab_pvals(seed):
    r = random.Random(seed)
    ps = [round(r.uniform(0.041, 0.0499), 4) for _ in range(30)] + [round(r.uniform(0.06, 0.9), 3) for _ in range(30)]
    rows = ["test,effect,p"] + ["t%d,%.2f,%s" % (i, r.uniform(0.1, 1), p) for i, p in enumerate(ps)]
    return "pvals.csv", "\n".join(rows) + "\n", ("p_values",)


def fab_decimals(seed):
    r = random.Random(seed)
    rows = ["firm,margin,rev"] + ["f%d,%d.375,%d" % (i, r.randint(1, 90), r.randint(1000, 9999)) for i in range(40)]
    return "decimals.csv", "\n".join(rows) + "\n", ("identical_decimals",)


def fab_json(seed):
    r = random.Random(seed)
    rows = [{"firm": "f%d" % i, "revenue": r.choice([100, 200, 250, 500, 1000, 1500, 2000, 5000]) * r.choice([1, 10, 100]), "p": 1.4 if i == 7 else round(r.random(), 3)} for i in range(60)]
    return "fake.json", json.dumps(rows), ("round", "impossible")


FABRICATED = [fab_uniform_digits, fab_round, fab_grim, fab_duplicates, fab_impossible,
              fab_impossible_pct, fab_total, fab_step, fab_pvals, fab_decimals, fab_json]
REAL_SHAPED = [lognormal_csv, pareto_csv, stats_table_md, total_table_csv]
