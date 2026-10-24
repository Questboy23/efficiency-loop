#!/usr/bin/env python3
"""wt: git worktree toolkit for running Claude Code agents in parallel.

Each agent gets its own worktree (a separate folder with its own branch that
shares the repo's history), so parallel agents never edit the same files.

Commands
  new NAME            make a worktree with env files copied and its own port
  ls                  list worktrees made by wt
  rm NAME             remove a worktree and its branch
  merge NAME          merge a worktree's branch into the current branch, then remove it
  bg NAME -- CMD      run a long command inside a worktree in the background
  tourney PROMPT      best-of-N: N agents on the same prompt, keep the winner
  ab PROMPT           harness off vs harness on, same prompt, side by side
  fcc PROMPT          run on the free proxy in a throwaway worktree, keep only if tests pass
  try PROMPT          hypothesis sandbox: keep the change only if a benchmark number improves

Every agent run appends one JSON line to <repo>/.wt/runs.jsonl.
Standard library only. Python 3.9+.
"""
import argparse, fnmatch, json, os, re, shlex, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CLAUDE = os.environ.get("WT_CLAUDE", "claude")
TOOLS = "Bash,Read,Edit,Write,Glob,Grep,Agent,Task"
COPY_PATTERNS = [".env", ".env.*", "*.local", ".dev.vars"] + \
    [p for p in os.environ.get("WT_COPY", "").split(",") if p]
BASE_PORT = int(os.environ.get("WT_BASE_PORT", "3100"))
# free-claude-code proxy; override if your proxy listens elsewhere
FCC_URL = os.environ.get("FCC_BASE_URL", "http://localhost:8082")
FCC_TOKEN = os.environ.get("FCC_AUTH_TOKEN", "freecc")
MAX_PARALLEL = int(os.environ.get("WT_MAX_PARALLEL", "4"))


# ---------- git helpers ----------

def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def repo_root():
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("wt: not inside a git repository")
    common = Path(r.stdout.strip())
    # main worktree is the parent of the shared .git dir
    return common.parent if common.name == ".git" else Path(git("rev-parse", "--show-toplevel"))


ROOT = None


def state_dir():
    d = ROOT / ".wt"
    d.mkdir(exist_ok=True)
    exclude = ROOT / ".git" / "info" / "exclude"
    if exclude.parent.exists():
        text = exclude.read_text() if exclude.exists() else ""
        if ".wt/" not in text:
            exclude.write_text(text + ("\n" if text and not text.endswith("\n") else "") + ".wt/\n.wt-port\n")
    return d


def wt_path(name):
    return ROOT.parent / f"{ROOT.name}.wt" / name


def branch_of(name):
    return f"wt/{name}"


def ensure_identity(cwd):
    if not git("config", "user.email", cwd=cwd, check=False):
        return ["-c", "user.email=wt@local", "-c", "user.name=wt"]
    return []


def commit_all(cwd, msg):
    git("add", "-A", cwd=cwd)
    if not git("status", "--porcelain", cwd=cwd):
        return False
    git(*ensure_identity(cwd), "commit", "-qm", msg, "--no-verify", cwd=cwd)
    return True


def diff_lines(cwd, base):
    out = git("diff", "--shortstat", f"{base}...HEAD", cwd=cwd, check=False)
    nums = [int(n) for n in re.findall(r"(\d+) (?:insertion|deletion)", out)]
    return sum(nums)


# ---------- worktree lifecycle ----------

def load_ports():
    f = state_dir() / "ports.json"
    return json.loads(f.read_text()) if f.exists() else {}


def save_ports(p):
    (state_dir() / "ports.json").write_text(json.dumps(p, indent=1))


def make_worktree(name, base=None, link_deps=False, quiet=False):
    path = wt_path(name)
    if path.exists():
        sys.exit(f"wt: {path} already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    base = base or git("rev-parse", "HEAD", cwd=ROOT)
    git("worktree", "add", "-q", "-b", branch_of(name), str(path), base, cwd=ROOT)

    # untracked files git does not carry into a new worktree (.env, keys)
    ignored = git("ls-files", "--others", "--ignored", "--exclude-standard", cwd=ROOT, check=False).splitlines()
    copied = []
    for rel in ignored:
        if "node_modules/" in rel or rel.startswith(".wt/"):
            continue
        if any(fnmatch.fnmatch(Path(rel).name, pat) for pat in COPY_PATTERNS):
            dst = path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
            copied.append(rel)

    if link_deps and (ROOT / "node_modules").is_dir() and not (path / "node_modules").exists():
        (path / "node_modules").symlink_to(ROOT / "node_modules")

    ports = load_ports()
    used = set(ports.values())
    port = next(BASE_PORT + 10 * i for i in range(1, 1000) if BASE_PORT + 10 * i not in used)
    ports[name] = port
    save_ports(ports)
    (path / ".wt-port").write_text(str(port))
    if not quiet:
        print(f"worktree  {path}\nbranch    {branch_of(name)}\nport      {port}  (PORT env in `wt bg`; also in .wt-port)")
        if copied:
            print("copied    " + ", ".join(copied))
    return path


def remove_worktree(name, keep_branch=False):
    path = wt_path(name)
    if path.exists():
        git("worktree", "remove", "--force", str(path), cwd=ROOT, check=False)
        shutil.rmtree(path, ignore_errors=True)
    git("worktree", "prune", cwd=ROOT, check=False)
    if not keep_branch:
        git("branch", "-D", branch_of(name), cwd=ROOT, check=False)
    ports = load_ports()
    if ports.pop(name, None) is not None:
        save_ports(ports)


def merge_worktree(name):
    path = wt_path(name)
    if path.exists():
        commit_all(path, f"wt: {name}")
    r = subprocess.run(["git", *ensure_identity(ROOT), "merge", "--no-ff", "-m", f"Merge {branch_of(name)}",
                        branch_of(name)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"merge conflict merging {branch_of(name)}; resolve in {ROOT}, worktree kept.\n{r.stdout}{r.stderr}")
    remove_worktree(name)
    print(f"merged {branch_of(name)} into {git('branch', '--show-current', cwd=ROOT)}")


# ---------- agent runs ----------

def agent_env(arm):
    env = dict(os.environ)
    for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        env.pop(k, None)
    if arm == "fcc":
        env["ANTHROPIC_BASE_URL"] = FCC_URL
        env["ANTHROPIC_AUTH_TOKEN"] = FCC_TOKEN
    return env


def run_agent(prompt, cwd, arm="plain", model=None, timeout=1800):
    cmd = [CLAUDE, "-p", prompt, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--allowedTools", TOOLS]
    if arm == "harness":
        cmd += ["--plugin-dir", str(PLUGIN_ROOT)]
    if model:
        cmd += ["--model", model]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=agent_env(arm))
        out = r.stdout
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "wall_s": round(time.time() - t0, 1)}
    res = {"wall_s": round(time.time() - t0, 1)}
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        res["error"] = "unparseable output: " + (out or r.stderr)[:300]
        return res
    u = data.get("usage") or {}
    res.update({
        "tokens": sum(u.get(k) or 0 for k in ("input_tokens", "cache_read_input_tokens",
                                              "cache_creation_input_tokens", "output_tokens")),
        "cost_usd": data.get("total_cost_usd"),
        "turns": data.get("num_turns"),
        "is_error": bool(data.get("is_error")),
    })
    return res


def run_shell(cmd, cwd, port=None, timeout=1800):
    if not cmd:
        return None, ""
    env = dict(os.environ)
    if port:
        env["PORT"] = str(port)
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode == 0, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return False, "timeout"


def log_run(rec):
    with open(state_dir() / "runs.jsonl", "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **rec}) + "\n")


def one_arm(tag, name, prompt, arm, test, model, base):
    path = make_worktree(name, base=base, quiet=True)
    port = int((path / ".wt-port").read_text())
    res = run_agent(prompt, path, arm=arm, model=model)
    commit_all(path, f"wt {tag}: {name}")
    passed, out = run_shell(test, path, port=port)
    rec = {"cmd": tag, "name": name, "arm": arm, "passed": passed,
           "diff_lines": diff_lines(path, base), **res}
    log_run({**rec, "prompt": prompt[:200]})
    rec["test_tail"] = out[-400:]
    return rec


def print_table(rows):
    print(f"{'name':<22}{'arm':<9}{'pass':<6}{'tokens':>10}{'diff':>7}{'wall_s':>8}  note")
    for r in rows:
        p = {True: "yes", False: "no", None: "-"}[r["passed"]]
        print(f"{r['name']:<22}{r['arm']:<9}{p:<6}{r.get('tokens') or 0:>10}{r['diff_lines']:>7}"
              f"{r.get('wall_s') or 0:>8}  {r.get('error') or ('agent error' if r.get('is_error') else '')}")


def rank_key(r):
    # passing first, then fewest tokens, then smallest diff
    return (0 if r["passed"] or r["passed"] is None and not r.get("error") else 1,
            r.get("tokens") or 10**12, r["diff_lines"])


def stamp():
    return time.strftime("%m%d-%H%M%S")


# ---------- commands ----------

def cmd_tourney(a):
    n = max(2, a.n)
    print(f"tourney: {n} agents, about {n}x the tokens of one run")
    base = git("rev-parse", "HEAD", cwd=ROOT)
    tag = f"t{stamp()}"
    arm = "fcc" if a.fcc else ("harness" if a.harness else "plain")
    with ThreadPoolExecutor(min(n, MAX_PARALLEL)) as ex:
        rows = list(ex.map(lambda i: one_arm("tourney", f"{tag}-{i}", a.prompt, arm, a.test, a.model, base), range(n)))
    rows.sort(key=rank_key)
    print_table(rows)
    win = rows[0]
    if a.test and not win["passed"]:
        print("no agent passed the test; all worktrees kept for inspection")
        return
    for r in rows[1:]:
        if not a.keep:
            remove_worktree(r["name"])
    print(f"winner {win['name']}  branch {branch_of(win['name'])}  path {wt_path(win['name'])}")
    if a.merge:
        merge_worktree(win["name"])
    else:
        print(f"merge with: wt merge {win['name']}")


def cmd_ab(a):
    base = git("rev-parse", "HEAD", cwd=ROOT)
    tag = f"ab{stamp()}"
    jobs = [(f"{tag}-off-{k}", "plain") for k in range(a.runs)] + [(f"{tag}-on-{k}", "harness") for k in range(a.runs)]
    with ThreadPoolExecutor(min(len(jobs), MAX_PARALLEL)) as ex:
        rows = list(ex.map(lambda j: one_arm("ab", j[0], a.prompt, j[1], a.test, a.model, base), jobs))
    print_table(rows)
    for arm in ("plain", "harness"):
        rs = [r for r in rows if r["arm"] == arm]
        passes = sum(1 for r in rs if r["passed"])
        toks = sum(r.get("tokens") or 0 for r in rs) / max(1, len(rs))
        label = "harness off" if arm == "plain" else "harness on "
        print(f"{label}: {passes}/{len(rs)} pass, {toks:,.0f} mean tokens")
    if not a.keep:
        for r in rows:
            remove_worktree(r["name"])
        print("worktrees removed (pass --keep to inspect); results in .wt/runs.jsonl")


def cmd_fcc(a):
    name = f"fcc{stamp()}"
    base = git("rev-parse", "HEAD", cwd=ROOT)
    print(f"fcc run via {FCC_URL}")
    r = one_arm("fcc", name, a.prompt, "fcc", a.test, a.model, base)
    print_table([r])
    ok = r["passed"] if a.test else not (r.get("error") or r.get("is_error"))
    if not ok:
        if a.keep_failed:
            print(f"failed; kept at {wt_path(name)}")
        else:
            remove_worktree(name)
            print("failed; worktree discarded. Test output tail:\n" + r["test_tail"])
        return
    if a.merge:
        merge_worktree(name)
    else:
        print(f"passed; review at {wt_path(name)}, then: wt merge {name}")


def metric(cmd, cwd):
    ok, out = run_shell(cmd, cwd)
    nums = re.findall(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", out)
    if not nums:
        sys.exit(f"wt try: bench printed no number (exit ok={ok}). Tail:\n{out[-400:]}")
    return float(nums[-1])


def cmd_try(a):
    base = git("rev-parse", "HEAD", cwd=ROOT)
    before = a.baseline if a.baseline is not None else metric(a.bench, ROOT)
    name = f"try{stamp()}"
    path = make_worktree(name, base=base, quiet=True)
    res = run_agent(a.prompt, path, arm=a.arm, model=a.model)
    commit_all(path, f"wt try: {name}")
    after = metric(a.bench, path)
    gain = (before - after) if a.lower_better else (after - before)
    keep = gain > a.min_gain
    log_run({"cmd": "try", "name": name, "arm": a.arm, "before": before, "after": after,
             "gain": gain, "kept": keep, "prompt": a.prompt[:200], **res})
    print(f"before {before:g}  after {after:g}  gain {gain:+g}  tokens {res.get('tokens') or 0:,}")
    if not keep:
        remove_worktree(name)
        print("no improvement; discarded")
    elif a.merge:
        merge_worktree(name)
    else:
        print(f"improved; kept at {path}. merge with: wt merge {name}")


def cmd_new(a):
    path = make_worktree(a.name, base=a.base, link_deps=a.link_deps)
    if a.claude:
        os.chdir(path)
        os.execvp(CLAUDE, [CLAUDE])  # replaces this process; run from the new folder
    print(f"start an agent there: cd {shlex.quote(str(wt_path(a.name)))} && claude")


def cmd_ls(a):
    ports = load_ports()
    out = git("worktree", "list", "--porcelain", cwd=ROOT)
    for block in out.split("\n\n"):
        lines = dict(l.split(" ", 1) for l in block.splitlines() if " " in l)
        br = lines.get("branch", "").replace("refs/heads/", "")
        if br.startswith("wt/"):
            name = br[3:]
            ahead = git("rev-list", "--count", f"HEAD..{br}", cwd=ROOT, check=False)
            print(f"{name:<24}port {ports.get(name, '-'):<6}{ahead or 0} commits ahead  {lines.get('worktree')}")


def cmd_bg(a):
    path = wt_path(a.name)
    if not path.exists():
        path = make_worktree(a.name, quiet=True)
    if not a.cmd:
        sys.exit("wt bg: give a command after --")
    log = state_dir() / f"{a.name}.log"
    env = dict(os.environ, PORT=(path / ".wt-port").read_text().strip())
    with open(log, "ab") as f:
        p = subprocess.Popen(" ".join(shlex.quote(c) for c in a.cmd), shell=True, cwd=path,
                             stdout=f, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    print(f"pid {p.pid} running in {path}\nlog {log}  (tail -f it)")


def main():
    global ROOT
    ap = argparse.ArgumentParser(prog="wt", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("new"); p.add_argument("name"); p.add_argument("--base")
    p.add_argument("--link-deps", action="store_true", help="symlink node_modules from the main checkout")
    p.add_argument("--claude", action="store_true", help="open claude in the new worktree")
    p.set_defaults(f=cmd_new)
    sp.add_parser("ls").set_defaults(f=cmd_ls)
    p = sp.add_parser("rm"); p.add_argument("name"); p.add_argument("--keep-branch", action="store_true")
    p.set_defaults(f=lambda a: (remove_worktree(a.name, a.keep_branch), print(f"removed {a.name}")))
    p = sp.add_parser("merge"); p.add_argument("name"); p.set_defaults(f=lambda a: merge_worktree(a.name))
    p = sp.add_parser("bg"); p.add_argument("name"); p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(f=cmd_bg)

    def agent_opts(p, test_required=False):
        p.add_argument("prompt")
        p.add_argument("--test", required=test_required, help="shell command; exit 0 means pass")
        p.add_argument("--model")

    p = sp.add_parser("tourney"); agent_opts(p)
    p.add_argument("-n", type=int, default=3)
    p.add_argument("--fcc", action="store_true", help="run every agent on the free proxy")
    p.add_argument("--harness", action="store_true", help="run every agent with this plugin loaded")
    p.add_argument("--merge", action="store_true"); p.add_argument("--keep", action="store_true")
    p.set_defaults(f=cmd_tourney)
    p = sp.add_parser("ab"); agent_opts(p)
    p.add_argument("--runs", type=int, default=1, help="runs per arm")
    p.add_argument("--keep", action="store_true"); p.set_defaults(f=cmd_ab)
    p = sp.add_parser("fcc"); agent_opts(p)
    p.add_argument("--merge", action="store_true", help="merge automatically when the test passes")
    p.add_argument("--keep-failed", action="store_true"); p.set_defaults(f=cmd_fcc)
    p = sp.add_parser("try"); p.add_argument("prompt"); p.add_argument("--model")
    p.add_argument("--bench", required=True, help="command whose last printed number is the metric")
    p.add_argument("--lower-better", action="store_true")
    p.add_argument("--baseline", type=float, help="skip measuring the current checkout")
    p.add_argument("--min-gain", type=float, default=0.0)
    p.add_argument("--arm", choices=["plain", "harness", "fcc"], default="fcc",
                   help="default fcc: hypothesis loops are mistake-tolerant")
    p.add_argument("--merge", action="store_true"); p.set_defaults(f=cmd_try)

    a = ap.parse_args()
    ROOT = repo_root()
    a.f(a)


if __name__ == "__main__":
    main()
