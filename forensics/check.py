#!/usr/bin/env python3
"""forensics.check: tripwire for fake, hand-typed or hallucinated data.

Usage: check.py FILE. Exit 0 and no output when the file looks fine or holds
fewer than 50 numbers. Exit 2 with a message on stderr when it trips.
Pure standard library. Tables are parsed into columns with headers, and the
statistical tests run per column. Statistical p-values are Holm-corrected
across every test run on the file; rule-based tests trip on a single hit.
"""
import csv
import io
import json
import math
import re
import sys
from collections import Counter

MAX_BYTES = 8_000_000      # read cap
MAX_ROWS = 2000            # larger tables are sampled at even spacing to stay under 150 ms
MIN_NUMBERS = 50
ALPHA = 0.001              # family-wise level after Holm
BENFORD_MAD = 0.015        # Nigrini nonconformity, first digit
BENFORD2_MAD = 0.012       # Nigrini nonconformity, second digit
MSG = ("Do not hand-edit these numbers. Find where they came from, regenerate "
       "them with code from the real source, or label them clearly as "
       "illustrative. Then rerun forensics.")

NUM_RE = re.compile(r"^[-+]?\$?[-+]?(\d{1,3}(,\d{3})+|\d+)?(\.\d+)?%?$")
TEXT_NUM_RE = re.compile(r"(?<![\w.])[-+]?\d[\d,]*\.?\d*(?![\w])")


# ---------------------------------------------------------------- parsing
def parse_num(s):
    """Return float for a numeric cell, else None."""
    s = s.strip()
    if not s:
        return None
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except ValueError:
        pass
    if NUM_RE.match(s) and any(c.isdigit() for c in s):
        try:
            return float(s.replace(",", "").replace("$", "").replace("%", ""))
        except ValueError:
            return None
    return None


class Table:
    def __init__(self, name, headers, rows):
        self.name, self.headers, self.rows = name, headers, rows
        self.cols = [[r[i] if i < len(r) else "" for r in rows]
                     for i in range(len(headers))]
        self.vals = [[parse_num(c) for c in col] for col in self.cols]
        self.numeric = []
        for i, vs in enumerate(self.vals):
            nonempty = sum(1 for c in self.cols[i] if c.strip())
            got = sum(1 for v in vs if v is not None)
            if got >= 5 and got >= 0.8 * nonempty:
                self.numeric.append(i)

    def label(self, i):
        return "%s[%s]" % (self.name, self.headers[i])


def tokens(h):
    return [t for t in re.split(r"[^a-z0-9%]+", h.lower()) if t]


def make_table(name, grid):
    grid = [r for r in grid if any(c.strip() for c in r)]
    if len(grid) < 3:
        return None
    first = grid[0]
    header_like = any(parse_num(c) is None and c.strip() for c in first)
    if header_like and any(parse_num(c) is not None for c in grid[1]):
        return Table(name, [c.strip() or "col%d" % i for i, c in enumerate(first)], grid[1:])
    if header_like and len(grid) > 2:
        return Table(name, [c.strip() or "col%d" % i for i, c in enumerate(first)], grid[1:])
    return Table(name, ["col%d" % i for i in range(len(first))], grid)


def walk_json(obj, tables, leaves, name="json", depth=0):
    if len(tables) > 50 or depth > 8:
        return
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj) and len(obj) >= 3:
            keys = []
            for x in obj[:200]:
                for k in x:
                    if k not in keys and not isinstance(x[k], (dict, list)):
                        keys.append(k)
            keys = keys[:60]
            rows = [[("" if not isinstance(x.get(k), (int, float, str)) else str(x.get(k)))
                     if x.get(k) is not None else "" for k in keys] for x in obj]
            t = make_table(name, [list(map(str, keys))] + rows)
            if t:
                tables.append(t)
            for x in obj[:20]:
                for k, v in x.items():
                    if isinstance(v, (dict, list)):
                        walk_json(v, tables, leaves, name + "." + str(k), depth + 1)
            return
        for x in obj:
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                leaves.append(repr(x))
            else:
                walk_json(x, tables, leaves, name, depth + 1)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and v and all(isinstance(x, (int, float, str)) for x in v):
                continue
            walk_json(v, tables, leaves, name + "." + str(k), depth + 1)
        cols = {k: v for k, v in obj.items() if isinstance(v, list) and len(v) >= 3
                and all(isinstance(x, (int, float, str)) or x is None for x in v)}
        if cols:
            n = max(len(v) for v in cols.values())
            keys = list(cols)
            rows = [["" if i >= len(cols[k]) or cols[k][i] is None else str(cols[k][i])
                     for k in keys] for i in range(n)]
            t = make_table(name, [keys] + rows)
            if t:
                tables.append(t)
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                leaves.append(repr(v))


def md_tables(lines):
    tables, i, used = [], 0, set()
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and re.match(
                r"^\s*\|?\s*:?-{2,}", lines[i + 1].lstrip("| ")) or (
                lines[i].lstrip().startswith("|") and i + 1 < len(lines)
                and set(lines[i + 1].strip()) <= set("|-: ") and "-" in lines[i + 1]):
            j, grid = i, []
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                if j != i + 1:
                    cells = [c.strip().strip("*`") for c in lines[j].strip().strip("|").split("|")]
                    grid.append(cells)
                used.add(j)
                j += 1
            used.add(i + 1)
            t = make_table("md%d" % len(tables), grid)
            if t:
                tables.append(t)
            i = j
        else:
            i += 1
    return tables, used


def load(path):
    """Return (tables, text_values) from a file; text_values are raw strings."""
    with open(path, "rb") as f:
        raw = f.read(MAX_BYTES + 1)
    truncated = len(raw) > MAX_BYTES
    text = raw[:MAX_BYTES].decode("utf-8", "replace")
    if truncated:
        text = text[:text.rfind("\n") + 1] if "\n" in text else text
    lines = None
    if text.count("\n") > MAX_ROWS + 1:
        lines = text.split("\n")
        step = len(lines) // MAX_ROWS + 1
        text = "\n".join(lines[:1] + lines[1::step])
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    tables, leaves = [], []
    if ext in ("csv", "tsv"):
        delim = "\t" if ext == "tsv" else ","
        if ext == "csv" and text[:2000].count("\t") > text[:2000].count(","):
            delim = "\t"
        t = make_table("csv", list(csv.reader(io.StringIO(text), delimiter=delim)))
        if t:
            tables.append(t)
    elif ext == "json" and not truncated and lines is None:
        try:
            walk_json(json.loads(text), tables, leaves)
        except ValueError:
            pass
    if not tables and not leaves:
        lines = text.split("\n")
        tables, used = md_tables(lines)
        body = "\n".join(l for k, l in enumerate(lines) if k not in used)
        body = re.sub(r"```.*?```", " ", body, flags=re.S)
        leaves = [m for m in TEXT_NUM_RE.findall(body)
                  if not re.match(r"^(19|20)\d\d$", m) and parse_num(m) is not None]
    if leaves and not leaves_dense(text, leaves):
        leaves = []   # numbers scattered in prose or config (versions, ids, years, prices) are not one sample
    return tables, leaves


def leaves_dense(text, leaves):
    """True when loose numbers make up a large share of the file's word tokens (a bare list of values)."""
    toks = len(re.findall(r"[A-Za-z_]+|[-+]?\d[\d.,eE+-]*", text))
    return len(leaves) >= 0.5 * max(toks, 1)


# ------------------------------------------------------------------ stats
def chi_sq_p(x, df):
    """Upper tail of chi-square: regularized Q(df/2, x/2)."""
    a, x = df / 2.0, x / 2.0
    if x <= 0:
        return 1.0
    if x < a + 1:
        s, term, n = 1.0 / a, 1.0 / a, a
        for _ in range(500):
            n += 1
            term *= x / n
            s += term
            if abs(term) < abs(s) * 1e-14:
                break
        return max(0.0, 1.0 - s * math.exp(-x + a * math.log(x) - math.lgamma(a)))
    b, c, d = x + 1 - a, 1e300, 1.0 / (x + 1 - a)
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        h *= d * c
        if abs(d * c - 1) < 1e-14:
            break
    return min(1.0, math.exp(-x + a * math.log(x) - math.lgamma(a)) * h)


def chi_sq(obs, exp_p):
    n = sum(obs)
    return sum((o - n * e) ** 2 / (n * e) for o, e in zip(obs, exp_p) if e > 0)


def binom_upper(k, n, p):
    """P(X >= k) for X~Bin(n,p); exact for small n, normal approx otherwise."""
    if k <= 0:
        return 1.0
    if n > 2000:
        z = (k - 0.5 - n * p) / math.sqrt(n * p * (1 - p))
        return 0.5 * math.erfc(z / math.sqrt(2))
    lp, lq = math.log(p), math.log(1 - p)
    tot = 0.0
    for i in range(k, n + 1):
        tot += math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                        + i * lp + (n - i) * lq)
    return min(1.0, tot)


_SIG = {}


def sig_digits(raw):
    r = _SIG.get(raw)
    if r is None:
        r = _SIG[raw] = _sig_digits(raw)
    return r


def _sig_digits(raw):
    """Significant digit string of a raw numeric cell, or '' if unusable."""
    s = raw.strip().lstrip("+-$").replace(",", "").rstrip("%")
    if "e" in s.lower():
        return ""
    s = s.replace(".", "").lstrip("0")
    return s if s.isdigit() else ""


def first_second(v):
    if v == 0:
        return None, None
    m = abs(v) / 10 ** math.floor(math.log10(abs(v)))
    d1 = int(m)
    d2 = int((m - d1) * 10 + 1e-9)
    return min(d1, 9), min(d2, 9)


SKIP_BENFORD = {"fips", "geoid", "tract", "place", "county", "state", "p", "pval", "pvalue", "prob", "probability", "pct", "percent", "percentile", "rank", "code",
                "id", "zip", "ccn", "phone", "year", "date", "expected", "share", "frac", "weight", "score",
                "offset", "byte", "index", "idx", "n", "count", "corr", "ic", "r", "z", "t", "sd", "std"}


def benford(col_vals, label, out, header=""):
    if set(tokens(header)) & SKIP_BENFORD or any(h in header.lower() for h in ("pct", "rank", "code", "prob")):
        return
    pos = [v for v in col_vals if v is not None and v > 0]
    n = len(pos)
    if n < 100 or max(pos) / min(pos) < 100:
        return
    fd = [first_second(v) for v in pos]
    obs = [0] * 9
    for a, _ in fd:
        obs[a - 1] += 1
    exp = [math.log10(1 + 1.0 / d) for d in range(1, 10)]
    mad = sum(abs(o / n - e) for o, e in zip(obs, exp)) / 9
    p = chi_sq_p(chi_sq(obs, exp), 8)
    out.append(dict(test="benford_first_digit", col=label, p=p, gate=mad > BENFORD_MAD, mad=mad,
                    detail="n=%d, share of leading 1 = %.1f%% (expected 30.1%%), MAD=%.4f (limit %.3f)"
                           % (n, 100.0 * obs[0] / n, mad, BENFORD_MAD),
                    nums=[]))
    if n >= 300:
        obs2 = [0] * 10
        for _, b in fd:
            obs2[b] += 1
        exp2 = [sum(math.log10(1 + 1.0 / (10 * a + b)) for a in range(1, 10)) for b in range(10)]
        mad2 = sum(abs(o / n - e) for o, e in zip(obs2, exp2)) / 10
        out.append(dict(test="benford_second_digit", col=label,
                        p=chi_sq_p(chi_sq(obs2, exp2), 9), gate=mad2 > BENFORD2_MAD,
                        detail="n=%d, MAD=%.4f (limit %.3f)" % (n, mad2, BENFORD2_MAD), nums=[]))


ID_TOK = {"ms", "duration", "timestamp", "epoch", "code", "id", "ccn", "zip", "phone", "year", "date", "npi", "cpt", "hcpcs", "ndc", "sha", "offset", "byte", "index", "idx", "fips", "geoid", "tract", "place", "county", "state", "gid", "fid", "uid"}


def is_id(header):
    return bool(set(tokens(header)) & ID_TOK) or header.lower().endswith(("_id", "_code"))


def codey(raw_col, vals):
    """Zero-padded fixed-width codes and arithmetic-progression indexes are labels, not measurements."""
    raw = [c.strip() for c in raw_col if c.strip()]
    if len(raw) >= 30:
        pad = [c for c in raw if len(c) >= 4 and c[0] == "0" and c.isdigit()]
        if len(pad) >= 0.1 * len(raw) and len({len(c) for c in raw}) == 1:
            return True   # constant width with leading zeros: a code column
    nv = [v for v in vals if v is not None]
    if len(nv) >= 30:
        steps = Counter(b - a for a, b in zip(nv, nv[1:]))
        if steps.most_common(1)[0][1] >= 0.95 * (len(nv) - 1) and steps.most_common(1)[0][0] > 0:
            return True
    return False


def last_digit(raw_col, label, out, header=""):
    if is_id(header):
        return
    ds = [sig_digits(c) for c in raw_col]
    ds = [d for d in ds if len(d) >= 3]
    obs = Counter(d[-1] for d in ds if d[-1] != "0")   # 0 is dropped: trailing zeros get stripped on export
    n = sum(obs.values())
    if n < 50:
        return
    o = [obs.get(str(k), 0) for k in range(1, 10)]
    x = chi_sq(o, [1 / 9.0] * 9)
    v = math.sqrt(x / (n * 8))
    out.append(dict(test="last_digit_uniformity", col=label, p=chi_sq_p(x, 8), gate=v > 0.25,
                    detail="n=%d, last-digit counts 1-9 = %s, Cramer V=%.2f" % (n, o, v), nums=[]))


COUNT_TOK = {"n", "count", "num", "size", "obs", "trials", "horizon", "window", "top", "lookback", "k", "days", "d", "h", "t"}


def round_excess(raw_col, label, out, header=""):
    if set(tokens(header)) & COUNT_TOK or is_id(header):
        return
    ints = [c.strip().replace(",", "") for c in raw_col]
    ints = [c for c in ints if re.match(r"^\d{3,}$", c)]
    n = len(ints)
    if n < 30 or len(set(ints)) < 8:
        return
    k = sum(1 for c in ints if c[-1] in "05")
    rnd = [c for c in ints if c[-1] in "05"]
    if n >= 300 and max(len(c) for c in ints) - min(len(c) for c in ints) >= 3 and sum(1 for c in rnd if c.endswith("000")) >= 0.5 * len(rnd):
        return   # amounts spanning 3+ orders of magnitude with thousands-rounded values in 300+ rows: raised/sold money, not typing
    out.append(dict(test="round_number_excess", col=label, p=binom_upper(k, n, 0.2),
                    gate=0.5 <= k / n < 0.98,   # 100% means a unit granularity (feet in fives), not typing
                    detail="%d of %d integers (%.0f%%) end in 0 or 5, expected 20%%" % (k, n, 100.0 * k / n),
                    nums=[c for c in ints if c[-1] in "05"][:8]))


# ------------------------------------------------------- rule-based tests
def hit(test, col, detail, nums):
    return dict(test=test, col=col, p=None, gate=True, detail=detail, nums=nums[:8])


NOT_PCT = {"roi", "excess", "alpha", "beta", "cagr", "pnl", "profit", "growth", "change", "increase", "return", "returns", "yoy", "diff", "delta",
           "gain", "ret", "chg", "rate", "markup", "premium", "ratio", "exposure", "leverage", "gross", "net", "utilization"}


def impossible(t, out):
    for i in t.numeric:
        toks = set(tokens(t.headers[i]))
        vals = [v for v in t.vals[i] if v is not None]
        label = t.label(i)
        if toks & {"p", "pval", "pvalue", "prob", "probability"} or {"p", "value"} <= toks:
            bad = [v for v in vals if v < 0 or v > 1]
            if bad:
                out.append(hit("impossible_probability", label, "%d values outside [0,1]" % len(bad), bad))
        elif ("%" in t.headers[i] or toks & {"pct", "percent", "percentage"}) and not toks & NOT_PCT:
            bad = [v for v in vals if v > 100]
            if bad:
                out.append(hit("impossible_percentage", label, "%d percentages above 100" % len(bad), bad))
        if toks & {"sd", "std", "stdev", "stddev", "se", "sem", "variance", "var"} or "std" in t.headers[i].lower():
            bad = [v for v in vals if v < 0]
            if bad:
                out.append(hit("negative_sd", label, "%d negative SD/variance values" % len(bad), bad))
        elif toks & {"count", "counts", "n", "num", "number", "freq", "frequency"} or t.headers[i].lower().startswith(("n_", "num_", "count")):
            bad = [v for v in vals if v < 0]
            if bad:
                out.append(hit("negative_count", label, "%d negative counts" % len(bad), bad))


def is_n_col(h):
    toks = tokens(h)
    return toks in (["n"], ["count"], ["samplesize"]) or toks[:1] == ["n"] and len(toks) <= 2 \
        or "sample" in toks and "size" in toks or "respondents" in toks


def grim(t, out):
    ncols = [i for i in t.numeric if is_n_col(t.headers[i])]
    if not ncols:
        return
    nc = ncols[0]
    hint_words = {"score", "rating", "likert", "count", "item", "response", "age", "grade", "points"}
    int_cols = [i for i in t.numeric if any(w in t.headers[i].lower() for w in ("min", "max"))
                and all(v is None or v == int(v) for v in t.vals[i])]
    for i in t.numeric:
        toks = set(tokens(t.headers[i]))
        if not (toks & {"mean", "avg", "average", "m"}):
            continue
        if not (toks & hint_words or int_cols):
            continue            # mean of possibly continuous data: GRIM does not apply
        bad = []
        for raw, v, nv in zip(t.cols[i], t.vals[i], t.vals[nc]):
            if v is None or nv is None or nv != int(nv) or nv < 2 or "." not in raw:
                continue
            d = len(raw.strip().split(".")[1])
            n = int(nv)
            if 10 ** d <= n:
                continue
            k = round(v * n)
            if abs(round(k / n, d) - v) > 0.5 * 10 ** (-d) * 0.01 + 1e-9:
                bad.append("%s (n=%d)" % (raw.strip(), n))
        if len(bad) >= 2:
            out.append(hit("grim_inconsistent_mean", t.label(i),
                           "%d means cannot come from integer data with the stated n" % len(bad), bad))


def row_label(t, r):
    for c in t.cols[:2]:
        if c and not parse_num(c[r]) and c[r].strip():
            return c[r].strip().lower()
    return ""


def close(a, b):
    return abs(a - b) <= max(1.0, 1e-4 * max(abs(a), abs(b)))


def arithmetic(t, out):
    n = len(t.rows)
    tot_rows = [r for r in range(n) if row_label(t, r) in ("total", "sum", "grand total", "totals", "all")]
    for i in t.numeric:
        for r in tot_rows:
            stated = t.vals[i][r]
            if stated is None:
                continue
            above = [t.vals[i][k] for k in range(r) if k not in tot_rows and t.vals[i][k] is not None]
            since = [t.vals[i][k] for k in range(max([x for x in tot_rows if x < r] + [-1]) + 1, r)
                     if t.vals[i][k] is not None]
            if len(above) >= 2 and not close(sum(above), stated) and not close(sum(since), stated):
                out.append(hit("total_mismatch", t.label(i),
                               "stated total %s but rows sum to %s" % (t.cols[i][r].strip(), round(sum(above), 4)),
                               [stated, sum(above)]))
    for ti in t.numeric:
        if not set(tokens(t.headers[ti])) & {"total", "sum", "tot"}:
            continue
        others = [i for i in t.numeric if i < ti and i != ti]
        if len(others) < 2:
            continue
        rows_ok, rows_bad = [], []
        for r in range(n):
            if t.vals[ti][r] is None or any(t.vals[i][r] is None for i in others):
                continue
            s = sum(t.vals[i][r] for i in others)
            (rows_ok if close(s, t.vals[ti][r]) else rows_bad).append((t.vals[ti][r], s))
        # a total above the shown columns' sum is usually an unshown category (missing, other); only a total below it is impossible
        if rows_bad and len(rows_ok) >= len(rows_bad) and any(a < b for a, b in rows_bad):
            out.append(hit("row_total_mismatch", t.label(ti),
                           "%d rows where stated total differs from the sum of columns to its left" % len(rows_bad),
                           [x for pair in rows_bad[:4] for x in pair]))


EXCL_STEP = {"id", "index", "idx", "year", "date", "rank", "row", "time", "t", "x", "day", "month",
             "week", "bin", "lag", "age", "grid", "step", "iter", "epoch", "ccn", "no", "num", "year_month", "quarter"}


def _sweep_partner(t, i):
    """A parameter grid cycles one column while another holds in runs (nested loops); that is code output, not typing."""
    for j in t.numeric:
        if j == i:
            continue
        vs = [v for v in t.vals[j] if v is not None]
        if len(vs) > 1 and len(set(vs)) <= 12 and sum(1 for k in range(len(vs) - 1) if vs[k] == vs[k + 1]) >= len(vs) / 2:
            return True
    return False


def too_perfect(t, out):
    for i in t.numeric:
        toks = set(tokens(t.headers[i]))
        vals = [v for v in t.vals[i] if v is not None]
        raws = [c for c, v in zip(t.cols[i], t.vals[i]) if v is not None]
        if toks & {"p", "pval", "pvalue"} or {"p", "value"} <= toks:
            below = [v for v in vals if 0.04 <= v < 0.05]
            above = [v for v in vals if 0.05 <= v < 0.06]
            m = len(below) + len(above)
            high = sum(1 for v in vals if v >= 0.06)
            if len(below) >= 8 and high >= 0.2 * len(vals) and binom_upper(len(below), m, 0.5) < 0.001:
                out.append(hit("p_values_just_under_0.05", t.label(i),
                               "%d p-values in [0.04,0.05) vs %d in [0.05,0.06)" % (len(below), len(above)), below))
        if len(vals) >= 10 and not toks & EXCL_STEP and not any(h in t.headers[i].lower() for h in ("year", "date", "id")):
            diffs = [vals[k + 1] - vals[k] for k in range(len(vals) - 1)]
            if abs(diffs[0]) > max(1e-6, 1e-3 * max(abs(v) for v in vals)) and abs(diffs[0]) != 1 and all(abs(d - diffs[0]) <= 1e-9 * max(1, abs(diffs[0])) for d in diffs):
                out.append(hit("constant_step", t.label(i),
                               "all %d consecutive differences equal %s" % (len(diffs), round(diffs[0], 6)), vals[:6]))
        ints = [int(v) for v in vals if v == int(v)]
        if len(ints) == len(vals) >= 30 and len(set(ints)) <= 12 and max(abs(v) for v in ints) <= 20 and not toks & (EXCL_STEP | {"hour", "minute", "dow", "weekday", "k", "fold", "seed", "group", "batch", "cluster", "level", "trial", "rep", "replicate", "sample"}):
            for per in range(2, 13):
                if len(ints) >= 3 * per and len(set(ints[:per])) == per and all(ints[k] == ints[k % per] for k in range(len(ints))) \
                        and not _sweep_partner(t, i):
                    out.append(hit("cyclic_values", t.label(i),
                                   "all %d values repeat the same %d-value cycle %s" % (len(ints), per, ints[:per]), ints[:2 * per]))
                    break
        decs = [c.strip().split(".")[1] for c in raws if "." in c.strip() and "e" not in c.lower()]
        if len(raws) >= 10 and len(decs) >= 0.8 * len(raws):
            top, cnt = Counter(decs).most_common(1)[0]
            if len(top) >= 3 and cnt >= 0.8 * len(raws) and cnt >= 8:
                out.append(hit("identical_decimals", t.label(i),
                               ".%s is the decimal part of %d of %d values" % (top, cnt, len(raws)),
                               [c for c in raws if c.strip().endswith("." + top)]))


def ordering(t, out):
    """Rows where a stated high is below open/close/low, or max/min fall on the wrong side of mean/median."""
    def col(*names):
        for i in t.numeric:
            if "_".join(tokens(t.headers[i])) in names:
                return i
        return None
    rules = [("high", ["high"], ["open", "close", "low"], "ge"), ("low", ["low"], ["open", "close", "high"], "le"),
             ("max", ["max", "maximum", "max_score"], ["mean", "median", "min", "avg"], "ge"),
             ("min", ["min", "minimum", "min_score"], ["mean", "median", "max", "avg"], "le")]
    for name, tops, others, op in rules:
        a = col(*tops)
        if a is None:
            continue
        for oname in others:
            b = col(oname)
            if b is None:
                continue
            bad = [r for r in range(len(t.rows)) if t.vals[a][r] is not None and t.vals[b][r] is not None
                   and (t.vals[a][r] < t.vals[b][r] - 1e-9 if op == "ge" else t.vals[a][r] > t.vals[b][r] + 1e-9)]
            if len(bad) >= 2 and len(bad) >= 0.02 * len(t.rows):   # real price feeds carry a few bad rows
                out.append(hit("ordering_violation", t.label(a),
                               "%d rows have %s %s than %s (e.g. %s vs %s)" % (len(bad), name, "below" if op == "ge" else "above", oname,
                                                                              t.cols[a][bad[0]].strip(), t.cols[b][bad[0]].strip()),
                               [t.cols[a][r].strip() for r in bad]))


def duplicates(t, out):
    n = len(t.rows)
    if n < 10:
        return
    big = n > 1000            # large exports legitimately repeat rows
    num_idx = t.numeric
    if len(num_idx) >= 3 and not big:
        keyc, first = Counter(), {}
        txt = [i for i in range(len(t.cols)) if i not in num_idx]
        for r in range(n):
            vs = tuple(t.cols[i][r].strip() for i in num_idx)
            if sum(1 for i in num_idx if len(sig_digits(t.cols[i][r])) >= 4) >= 3:
                if vs in first:
                    # copy-paste leaves at most one text cell (the label) different
                    other = first[vs]
                    # (rows identical in every cell are export duplicates, not evidence)
                    if [i for i in txt if t.cols[i][r] != t.cols[i][other]] == txt[:1]:
                        keyc[vs] += 1
                else:
                    first[vs] = r
        keyc = Counter({k: c + 1 for k, c in keyc.items()})
        dup = sum(c - 1 for c in keyc.values() if c > 1)
        if dup >= 3 and dup / n >= 0.1:
            worst = max(keyc, key=keyc.get)
            out.append(hit("duplicate_rows", t.name,
                           "%d of %d rows repeat the numeric fields of another row" % (dup, n), list(worst)))
    for i in num_idx:
        vals = [c.strip() for c, v in zip(t.cols[i], t.vals[i]) if v is not None and len(sig_digits(c)) >= 5 and "." in c]
        if len(vals) >= 20:
            top, cnt = Counter(vals).most_common(1)[0]
            if cnt >= 6 and 0.4 <= cnt / len(vals) <= 0.7 and float(top) != int(float(top)):   # a fully constant column is a parameter, not a copy
                out.append(hit("repeated_identical_value", t.label(i),
                               "%s appears %d times in %d values" % (top, cnt, len(vals)), [top] * 3))


# ------------------------------------------------------------------- main
PAIR_MAD = 0.05


def analyze(path):
    tables, leaves = load(path)
    nums = sum(sum(1 for v in t.vals[i] if v is not None) for t in tables for i in t.numeric) + len(leaves)
    res = dict(path=path, n_numbers=nums, findings=[], tripped=False, tests_run=0)
    if nums < MIN_NUMBERS:
        return res
    f = []
    for t in tables:
        impossible(t, f)
        grim(t, f)
        arithmetic(t, f)
        too_perfect(t, f)
        duplicates(t, f)
        ordering(t, f)
        for i in t.numeric:
            nv = [v for v in t.vals[i] if v is not None]
            if len(nv) >= 200 and len(set(nv)) < 0.2 * len(nv):
                continue
            if codey(t.cols[i], t.vals[i]):
                continue   # few distinct values in a long column: categories or price points, digit tests do not apply
            benford(t.vals[i], t.label(i), f, t.headers[i])
            last_digit(t.cols[i], t.label(i), f, t.headers[i])
            round_excess(t.cols[i], t.label(i), f, t.headers[i])
    if leaves:
        lv = [parse_num(x) for x in leaves]
        benford(lv, "text", f)
        last_digit(leaves, "text", f)
        round_excess(leaves, "text", f)
    stat = sorted((x for x in f if x["p"] is not None), key=lambda x: x["p"])
    m = len(stat)
    res["tests_run"] = m
    reject = True
    for rank, x in enumerate(stat):
        reject = reject and x["p"] <= ALPHA / (m - rank)
        x["holm_reject"] = reject
    hot = [x for x in stat if x.get("holm_reject") and x["gate"]]
    fam = lambda x: x["test"].split("_")[0]
    percol = Counter()
    for c in {x["col"] for x in hot}:
        percol[c] = len({fam(x) for x in hot if x["col"] == c})
    # A single digit-statistic flag is weak (rounded exports, ratios and bounded
    # quantities all trip them), so statistical tests need two flags on one column.
    trips = [x for x in f if x["p"] is None and x["gate"]]
    # Benford plus last-digit alone is also weak: bounded or rounded real columns (rates, prices)
    # trip both together. That pair needs a first-digit MAD of PAIR_MAD or more (uniform leading digits give 0.057).
    def strong(c):
        fams = {fam(x) for x in hot if x["col"] == c}
        if fams == {"benford", "last"}:
            return max(x.get("mad", 0) for x in hot if x["col"] == c) >= PAIR_MAD
        return len(fams) >= 2
    trips += [x for x in hot if strong(x["col"]) or x["test"] == "round_number_excess"]
    res["findings"] = trips
    res["tripped"] = bool(trips)
    res["score"] = min([x["p"] for x in trips if x["p"] is not None] + [1.0])
    return res


def format_message(res):
    lines = ["FORENSICS TRIPPED on %s (%d numbers checked):" % (res["path"], res["n_numbers"])]
    for x in res["findings"][:6]:
        s = "- %s in %s: %s" % (x["test"], x["col"], x["detail"])
        if x["p"] is not None:
            s += " (p=%.2g)" % x["p"]
        if x["nums"]:
            s += ". Numbers: " + ", ".join(str(n) for n in x["nums"][:8])
        lines.append(s)
    lines.append(MSG)
    return "\n".join(lines)


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: check.py FILE\n")
        return 1
    try:
        res = analyze(argv[1])
    except (OSError, UnicodeError):
        return 0
    if res["tripped"]:
        sys.stderr.write(format_message(res) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
