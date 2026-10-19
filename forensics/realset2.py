#!/usr/bin/env python3
"""Second real-file set: CSV/TSV files under ~ (depth <= 6) not in bench.real_files().
Same frozen split rule as heldout.py: md5(path) odd = held-out (count only, never inspect), even = dev.
Run: python3 forensics/realset2.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from forensics import bench, check
from forensics.heldout import is_heldout

SKIP = {"node_modules", "Library", "efficiency-loop", ".venv", "venv", "site-packages", "__pycache__"}


def files():
    known = set(bench.real_files())
    home = os.path.expanduser("~")
    out = []
    for root, dirs, fs in os.walk(home):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        if root[len(home):].count(os.sep) >= 6:
            dirs[:] = []
        for f in fs:
            p = os.path.join(root, f)
            if f.endswith((".csv", ".tsv")) and p not in known and os.path.getsize(p) >= 4000:
                out.append(p)
    return sorted(out)


def main():
    dev, held, devtrips = [0, 0], [0, 0], []
    for f in files():
        try:
            t = check.analyze(f)["tripped"]
        except Exception:
            continue
        side = held if is_heldout(f) else dev
        side[0] += bool(t); side[1] += 1
        if t and side is dev:
            devtrips.append(f)
    print("set2 dev FP %d/%d" % tuple(dev))
    print("set2 heldout FP %d/%d  (command: python3 forensics/realset2.py)" % tuple(held))
    for f in devtrips:
        print("dev trip:", f)


if __name__ == "__main__":
    main()
