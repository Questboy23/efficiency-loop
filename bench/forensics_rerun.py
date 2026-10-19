"""Rerun the forensics arm only, with the current detectors and the provenance flag on.
Command: EFFICIENCY_LOOP_PROVENANCE=on uv run python bench/forensics_rerun.py [--runs N]"""
import argparse, json, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import forensics_bench as fb

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="bench/forensics_rerun.jsonl")
ap.add_argument("--runs", type=int, default=2)
ap.add_argument("--workers", type=int, default=3)
a = ap.parse_args()
lock = threading.Lock()
jobs = [t for _ in range(a.runs) for t in fb.TASKS]
with ThreadPoolExecutor(max_workers=a.workers) as ex:
    list(ex.map(lambda t: fb.run_one(t, "forensics", a.out, lock, 900), jobs))
