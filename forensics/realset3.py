#!/usr/bin/env python3
"""Third real-file set: JSON, Markdown, TXT files under ~ (depth <= 6) not in bench.real_files().
Same frozen split rule as heldout.py: md5(path) odd = held-out (count only, never inspect), even = dev.
Run: python3 forensics/realset3.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from forensics import bench, check
from forensics.heldout import is_heldout

SKIP = {"node_modules", "Library", "efficiency-loop", "polyglot-benchmark", "skills-library", "plugins", "skills", ".venv", "venv", "site-packages", "__pycache__"}


def files():
    known = set()
    home = os.path.expanduser("~")
    out = []
    for root, dirs, fs in os.walk(home):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        if root[len(home):].count(os.sep) >= 6:
            dirs[:] = []
        for f in fs:
            p = os.path.join(root, f)
            if f.endswith((".json", ".md", ".txt")) and p not in known and os.path.getsize(p) >= 4000:
                out.append(p)
    # cap 3 files per directory (md5 order) so one cache dir cannot dominate
    import hashlib, collections
    per = collections.defaultdict(list)
    for p in sorted(out):
        per[os.path.dirname(p)].append(p)
    keep = []
    for d, ps in per.items():
        ps.sort(key=lambda p: hashlib.md5(p.encode()).hexdigest())
        keep += ps[:3]
    return sorted(keep)


def main():
    import collections
    bytest = collections.Counter()
    dev, held, devtrips = [0, 0], [0, 0], []
    for f in files():
        try:
            r = check.analyze(f); t = r["tripped"]
            if t: bytest.update({x["test"].split("_")[0] for x in r["findings"]})
        except Exception:
            continue
        side = held if is_heldout(f) else dev
        side[0] += bool(t); side[1] += 1
        if t and side is dev:
            devtrips.append(f)
    print("set3 dev FP %d/%d" % tuple(dev))
    print("set3 heldout FP %d/%d  (command: python3 forensics/realset3.py)" % tuple(held))
    print("trips by test family:", dict(bytest))
    for f in devtrips[:40]:
        print("dev trip:", f)


if __name__ == "__main__":
    main()
