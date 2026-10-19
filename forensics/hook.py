#!/usr/bin/env python3
"""Claude Code PostToolUse hook for Write|Edit|MultiEdit.

Reads the hook JSON on stdin. Runs check.py on data-like or report-like files,
and scans code written to disk for result arrays typed as literals or random
generators that write into results/report files. Exit 2 with the message on
stderr when it trips; exit 0 silently otherwise. Set EFFICIENCY_LOOP_FORENSICS=off
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


def edited_text(ti):
    parts = [ti.get("content") or "", ti.get("new_string") or ""]
    for e in ti.get("edits") or []:
        parts.append(e.get("new_string") or "")
    return "\n".join(parts)


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
    if low.endswith(DATA_EXT):
        try:
            res = check.analyze(path)
        except (OSError, UnicodeError):
            return 0
        if res["tripped"]:
            sys.stderr.write(check.format_message(res) + "\n")
            return 2
    elif path.endswith(CODE_EXT):
        found = code_findings(edited_text(ti))
        if found:
            sys.stderr.write("FORENSICS TRIPPED on %s:\n- %s\n%s\n" % (path, "\n- ".join(found), check.MSG))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
