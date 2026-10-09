#!/usr/bin/env python3
"""A/B harness: plain Claude Code vs Claude Code + efficiency layer.

Runs each benchmark task under each arm, grades it against the pristine test
file, and appends one JSON line per run to the results file. Re-running the same
command resumes where it stopped.

Example (pilot, ~40 runs):
  python3 run_ab.py --bench polyglot-benchmark/python/exercises/practice \
      --arms baseline,layer --tasks 10 --runs 2
"""
import argparse, json, os, random, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = "Bash,Read,Edit,Write,Glob,Grep,Agent,Task"


def find_tasks(bench: Path):
    tasks = []
    for d in sorted(bench.iterdir()):
        if not d.is_dir():
            continue
        tests = list(d.glob("*_test.py"))
        instr = d / ".docs" / "instructions.md"
        if tests and instr.exists():
            tasks.append(d)
    return tasks


def task_prompt(task: Path) -> str:
    docs = task / ".docs"
    parts = []
    for name in ("introduction.md", "instructions.md", "instructions.append.md"):
        p = docs / name
        if p.exists():
            parts.append(p.read_text())
    test = next(task.glob("*_test.py")).name
    stub = test.replace("_test.py", ".py")
    parts.append(f"Implement the solution in {stub} so that every test in {test} passes. "
                 f"Do not modify {test}. Use only the Python standard library.")
    return "\n\n".join(parts)


def prepare_workdir(task: Path) -> Path:
    wd = Path(tempfile.mkdtemp(prefix=f"ab_{task.name}_"))
    for item in task.iterdir():
        if item.name in (".meta",):  # .meta holds the reference solution; never expose it
            continue
        if item.is_dir():
            shutil.copytree(item, wd / item.name)
        else:
            shutil.copy2(item, wd / item.name)
    subprocess.run(["git", "init", "-q"], cwd=wd)
    subprocess.run(["git", "add", "-A"], cwd=wd)
    subprocess.run(["git", "-c", "user.email=ab@local", "-c", "user.name=ab", "commit", "-qm", "start"], cwd=wd)
    return wd


def call_claude(prompt, cwd, layer_file=None, model=None, max_turns=None, bare=False, timeout=1800):
    cmd = ["claude"]
    if bare:
        cmd.append("--bare")
    cmd += ["-p", prompt, "--output-format", "json",
            "--permission-mode", "acceptEdits", "--allowedTools", TOOLS]
    if layer_file:
        cmd += ["--append-system-prompt-file", str(layer_file)]
    if model:
        cmd += ["--model", model]
    if max_turns:
        cmd += ["--max-turns", str(max_turns)]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out, err = r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "wall_s": time.time() - t0}
    res = {"wall_s": round(time.time() - t0, 1)}
    try:
        data = json.loads(out.strip().splitlines()[-1] if out.strip() else "{}")
    except (json.JSONDecodeError, IndexError):
        res["error"] = "unparseable output: " + (out or err)[:300]
        return res
    usage = data.get("usage") or {}
    res.update({
        "cost_usd": data.get("total_cost_usd"),
        "num_turns": data.get("num_turns"),
        "duration_ms": data.get("duration_ms"),
        "tokens_in": (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
                     + (usage.get("cache_creation_input_tokens") or 0),
        "tokens_out": usage.get("output_tokens") or 0,
        "is_error": data.get("is_error"),
        "result_text": (data.get("result") or "")[-600:],
    })
    return res


def grade(task: Path, wd: Path, timeout=300):
    # Restore the pristine test file so edited tests cannot pass a run.
    for t in task.glob("*_test.py"):
        shutil.copy2(t, wd / t.name)
    test = next(task.glob("*_test.py")).name
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", test],
                           cwd=wd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True, help="folder of task folders (python/exercises/practice)")
    ap.add_argument("--arms", default="baseline,layer", help="any of baseline,layer,layer_rewrite plus --extra-arm names")
    ap.add_argument("--extra-arm", action="append", default=[], help="NAME=path/to/layer.md (for ablations)")
    ap.add_argument("--tasks", type=int, default=0, help="use only the first N tasks (0 = all)")
    ap.add_argument("--runs", type=int, default=2, help="runs per task per arm")
    ap.add_argument("--out", default="results.jsonl")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-turns", type=int, default=None, help="optional; only if your Claude Code version supports it")
    ap.add_argument("--bare", action="store_true", help="isolated runs; needs ANTHROPIC_API_KEY, not your subscription")
    ap.add_argument("--sleep", type=float, default=0, help="seconds between runs, to spread usage across limit windows")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    layers = {"baseline": None, "layer": HERE / "efficiency-layer.md", "layer_rewrite": HERE / "efficiency-layer.md"}
    for spec in a.extra_arm:
        name, path = spec.split("=", 1)
        layers[name] = Path(path).resolve()
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    for arm in arms:
        if arm not in layers:
            sys.exit(f"unknown arm {arm}")

    tasks = find_tasks(Path(a.bench))
    if a.tasks:
        tasks = tasks[: a.tasks]
    if not tasks:
        sys.exit("no tasks found; point --bench at python/exercises/practice")

    done = set()
    if os.path.exists(a.out):
        for line in open(a.out):
            try:
                r = json.loads(line)
                done.add((r["task"], r["arm"], r["run"]))
            except Exception:
                pass

    jobs = [(t, arm, i) for t in tasks for arm in arms for i in range(a.runs)]
    random.Random(a.seed).shuffle(jobs)  # random order so time-of-day effects hit all arms equally
    print(f"{len(tasks)} tasks x {len(arms)} arms x {a.runs} runs = {len(jobs)} runs "
          f"({len(done)} already done)")
    rewrite_instr = (HERE / "rewrite-prompt.md").read_text()

    for n, (task, arm, i) in enumerate(jobs, 1):
        if (task.name, arm, i) in done:
            continue
        prompt = task_prompt(task)
        if a.dry_run:
            print(f"[dry] {task.name} | {arm} | run {i} | layer={layers[arm]} | prompt {len(prompt)} chars")
            continue
        wd = prepare_workdir(task)
        rec = {"task": task.name, "arm": arm, "run": i, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        rewrite_cost = 0.0
        if arm == "layer_rewrite":
            rw = call_claude(rewrite_instr + "\n" + prompt, wd, model=a.model, bare=a.bare)
            new = (rw.get("result_text") or "").strip()
            rewrite_cost = rw.get("cost_usd") or 0.0
            rec["rewrite_ok"] = bool(new)
            if new:
                prompt = new
        res = call_claude(prompt, wd, layers[arm], a.model, a.max_turns, a.bare)
        res["passed"] = grade(task, wd) if "error" not in res else False
        if res.get("cost_usd") is not None:
            res["cost_usd"] = round(res["cost_usd"] + rewrite_cost, 5)
        res.pop("result_text", None)
        rec.update(res)
        with open(a.out, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[{n}/{len(jobs)}] {task.name:22s} {arm:14s} run {i}  passed={rec['passed']}  "
              f"cost={rec.get('cost_usd')}  turns={rec.get('num_turns')}")
        shutil.rmtree(wd, ignore_errors=True)
        if a.sleep:
            time.sleep(a.sleep)


if __name__ == "__main__":
    main()
