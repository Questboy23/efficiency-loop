#!/usr/bin/env python3
"""Frozen split of real CSV files: hash(path) odd = held-out (never inspect or tune on), even = dev.
Run: python3 forensics/heldout.py   prints FP counts for each half and names dev-half trips only."""
import hashlib, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from forensics import bench, check


def is_heldout(path):
    return int(hashlib.md5(path.encode()).hexdigest(), 16) % 2 == 1


def main():
    dev = [0, 0, []]
    held = [0, 0]
    for f in bench.real_files():
        try:
            tripped = check.analyze(f)["tripped"]
        except Exception:
            continue
        if is_heldout(f):
            held[0] += bool(tripped); held[1] += 1
        else:
            dev[0] += bool(tripped); dev[1] += 1
            if tripped:
                dev[2].append(f)
    print("dev FP %d/%d" % (dev[0], dev[1]))
    print("heldout FP %d/%d  (command: python3 forensics/heldout.py)" % (held[0], held[1]))
    for f in dev[2]:
        print("dev trip:", f)


if __name__ == "__main__":
    main()
