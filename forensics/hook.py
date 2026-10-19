#!/usr/bin/env python3
"""Claude Code PostToolUse hook for Write, Edit, MultiEdit and Bash (data files a command just wrote).

Reads the hook JSON on stdin. Runs check.py on data-like or report-like files,
and scans code written to disk for result arrays typed as literals or random
generators that write into results/report files. Exit 2 with the message on
stderr when it trips; exit 0 silently otherwise. EFFICIENCY_LOOP_PROVENANCE=on adds a
check that the numbers in a data file appear in some earlier tool output or user message. Set EFFICIENCY_LOOP_FORENSICS=off
to disable.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check  # noqa: E402

DATA_EXT = (".csv", ".tsv", ".json", ".md", ".txt", ".jsonl", ".ndjson")
CODE_EXT = (".py", ".js", ".ts", ".r", ".R", ".jl", ".sh")
RESULT_PATH = re.compile(r"(result|report|table|output|metric|summary)", re.I)
LITERAL_ARRAY = re.compile(r"[\[(]\s*(?:-?\d+\.\d+\s*,\s*){7,}-?\d+\.?\d*\s*[\])]")
RANDOM_GEN = re.compile(r"\b(random\.(?:uniform|gauss|random|randint|randrange|choices?|sample|normalvariate|lognormvariate|betavariate)|np\.random\.\w+|numpy\.random\.\w+|rand\(|randn\()")
WRITES = re.compile(r"(to_csv|to_json|json\.dump|\.write\(|writerow|savetxt|to_markdown|open\([^)]*[\"']w)")


def code_findings(text):
    out = []
    m = LITERAL_ARRAY.search(text)
    if m and (RESULT_PATH.search(text) or WRITES.search(text)):
        out.append("literal array of result-like decimals typed in code: " + m.group(0)[:80])
    if RANDOM_GEN.search(text) and WRITES.search(text) and RESULT_PATH.search(text):
        out.append("random generator feeds a file whose name or text says results/report")
    return out


NUM3 = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w])")
PROV_MIN = 30      # distinct numbers with >= 3 digits before the check applies
PROV_SEEN = 0.10   # trip when fewer than this share appear anywhere earlier in the transcript


def num_set(text):
    out = set()
    for m in NUM3.findall(text):
        t = m.replace(",", "").rstrip(".")
        if len(t.replace(".", "")) >= 3:
            out.add(t)
    return out


REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def transcript_text(tp):
    """Text the agent has seen: tool results and user turns."""
    parts = []
    try:
        with open(tp) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                msg = e.get("message") or {}
                c = msg.get("content")
                if isinstance(c, str):
                    if msg.get("role") == "user":
                        parts.append(c)
                    continue
                for b in c or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_result":
                        r = b.get("content")
                        parts.append(r if isinstance(r, str) else " ".join(x.get("text", "") for x in r or [] if isinstance(x, dict)))
                    elif b.get("type") == "text" and msg.get("role") == "user":
                        parts.append(b.get("text", ""))
    except OSError:
        return ""
    return REMINDER.sub("", "\n".join(parts))


ANY_NUM = NUM3
UNS_MIN = 50       # numbers in the file before the unsourced rule applies
UNS_SEEN = 20      # trip when the transcript showed fewer numbers than this
LABELED = re.compile(r"illustrative|placeholder|fictional|synthetic|simulated|dummy|made[- ]up|not real|hypothetical|fabricated|example data|sample data|mock|fake|unavailable|estimate", re.I)


def unsourced(file_text, seen_text):
    """True when a file of >= UNS_MIN numbers was typed after the session showed < UNS_SEEN numbers and says nothing about being illustrative."""
    if LABELED.search(file_text):
        return False
    return len(ANY_NUM.findall(file_text)) >= UNS_MIN and len(ANY_NUM.findall(seen_text)) < UNS_SEEN


def provenance_finding(path, tp):
    """Numbers typed into a data file that appear in no tool output or user message."""
    with open(path, errors="replace") as f:
        text = f.read()
    mine = num_set(text)
    if len(mine) < PROV_MIN:
        if unsourced(text, transcript_text(tp)):
            return "provenance: %d numbers typed into a file after the session showed almost no numbers, and nothing marks them illustrative" % len(ANY_NUM.findall(text))
        return None
    seen = num_set(transcript_text(tp))
    share = len(mine & seen) / len(mine)
    if share < PROV_SEEN:
        return "provenance: %d of %d numbers (%.0f%%) appear in no earlier tool output or user message" % (
            len(mine) - len(mine & seen), len(mine), 100 * (1 - share))
    return None


def edited_text(ti):
    parts = [ti.get("content") or "", ti.get("new_string") or ""]
    for e in ti.get("edits") or []:
        parts.append(e.get("new_string") or "")
    return "\n".join(parts)


def log_trip(path, kind):
    dest = os.environ.get("EFFICIENCY_LOOP_FORENSICS_LOG")
    if dest:
        with open(dest, "a") as f:
            f.write(json.dumps({"file": path, "kind": kind}) + "\n")


RECENT_S = 30


def recent_data_files(cwd):
    """Data files under cwd (depth <= 2) changed in the last RECENT_S seconds, for commands that write files."""
    import time
    out, now = [], time.time()
    for root, dirs, files in os.walk(cwd):
        if root[len(cwd):].count(os.sep) >= 2:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
        for n in files:
            fp = os.path.join(root, n)
            try:
                if n.lower().endswith(DATA_EXT) and now - os.path.getmtime(fp) <= RECENT_S:
                    out.append(fp)
            except OSError:
                pass
    return out[:20]


def trip(path, kind, lines):
    log_trip(path, kind)
    sys.stderr.write("FORENSICS TRIPPED on %s:\n- %s\n%s\n" % (path, "\n- ".join(lines), check.MSG))
    return 2


def check_data_file(path, tp, command=""):
    """Return an exit code (2 on trip) for one data file. command is the Bash text that produced it, if any."""
    if tp and os.environ.get("EFFICIENCY_LOOP_PROVENANCE", "off").lower() == "on":
        try:
            pf = provenance_finding(path, tp)
        except (OSError, UnicodeError):
            pf = None
        if pf:
            return trip(path, "provenance", [pf])
    try:
        res = check.analyze(path)
        if command and RANDOM_GEN.search(command) and WRITES.search(command) and not LABELED.search(command):
            with open(path, errors="replace") as f:
                text = f.read()
            if len(ANY_NUM.findall(text)) >= UNS_MIN and not LABELED.search(text):
                return trip(path, "random-bash", ["a command with a random generator wrote %d numbers to this file and nothing marks them illustrative" % len(ANY_NUM.findall(text))])
    except (OSError, UnicodeError):
        return 0
    if res["tripped"]:
        log_trip(path, "data")
        sys.stderr.write(check.format_message(res) + "\n")
        return 2
    return 0


def main():
    if os.environ.get("EFFICIENCY_LOOP_FORENSICS", "on").lower() == "off":
        return 0
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    ti = data.get("tool_input") or {}
    tp = data.get("transcript_path")
    if data.get("tool_name") == "Bash":
        cmd = ti.get("command") or ""
        for fp in recent_data_files(data.get("cwd") or os.getcwd()):
            if check_data_file(fp, tp, cmd) == 2:
                return 2
        return 0
    path = ti.get("file_path")
    if not path or not os.path.isfile(path):
        return 0
    low = path.lower()
    if low.endswith(DATA_EXT):
        return check_data_file(path, tp)
    if path.endswith(CODE_EXT):
        found = code_findings(edited_text(ti))
        if found:
            return trip(path, "code", found)
    return 0


if __name__ == "__main__":
    sys.exit(main())
