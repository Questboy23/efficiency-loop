#!/usr/bin/env python3
"""Claude Code PostToolUse hook for Write|Edit|MultiEdit.

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
RANDOM_GEN = re.compile(r"\b(random\.(?:uniform|gauss|random|randint|choice|normalvariate)|np\.random\.\w+|numpy\.random\.\w+|rand\(|randn\()")
WRITES = re.compile(r"(to_csv|to_json|json\.dump|\.write\(|writerow|savetxt|to_markdown|open\([^)]*[\"']w)")


def code_findings(text):
    out = []
    m = LITERAL_ARRAY.search(text)
    if m and (RESULT_PATH.search(text) or WRITES.search(text)):
        out.append("literal array of result-like decimals typed in code: " + m.group(0)[:80])
    if RANDOM_GEN.search(text) and WRITES.search(text) and RESULT_PATH.search(text):
        out.append("random generator feeds a file whose name or text says results/report")
    return out


NUM3 = re.compile(r"(?<![\w.])\d[\d,]*\.?\d*(?![\w])")
PROV_MIN = 30      # distinct numbers with >= 3 digits before the check applies
PROV_SEEN = 0.10   # trip when fewer than this share appear anywhere earlier in the transcript


def num_set(text):
    out = set()
    for m in NUM3.findall(text):
        t = m.replace(",", "").rstrip(".")
        if len(t.replace(".", "")) >= 3:
            out.add(t)
    return out


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
    return "\n".join(parts)


def provenance_finding(path, tp):
    """Numbers typed into a data file that appear in no tool output or user message."""
    with open(path, errors="replace") as f:
        mine = num_set(f.read())
    if len(mine) < PROV_MIN:
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


def main():
    if os.environ.get("EFFICIENCY_LOOP_FORENSICS", "on").lower() == "off":
        return 0
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    ti = data.get("tool_input") or {}
    path = ti.get("file_path")
    if not path or not os.path.isfile(path):
        return 0
    low = path.lower()
    tp = data.get("transcript_path")
    if low.endswith(DATA_EXT) and tp and os.environ.get("EFFICIENCY_LOOP_PROVENANCE", "off").lower() == "on":
        try:
            pf = provenance_finding(path, tp)
        except (OSError, UnicodeError):
            pf = None
        if pf:
            log_trip(path, "provenance")
            sys.stderr.write("FORENSICS TRIPPED on %s:\n- %s\n%s\n" % (path, pf, check.MSG))
            return 2
    if low.endswith(DATA_EXT):
        try:
            res = check.analyze(path)
        except (OSError, UnicodeError):
            return 0
        if res["tripped"]:
            log_trip(path, "data")
            sys.stderr.write(check.format_message(res) + "\n")
            return 2
    elif path.endswith(CODE_EXT):
        found = code_findings(edited_text(ti))
        if found:
            log_trip(path, "code")
            sys.stderr.write("FORENSICS TRIPPED on %s:\n- %s\n%s\n" % (path, "\n- ".join(found), check.MSG))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
