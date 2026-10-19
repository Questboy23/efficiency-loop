"""Provenance false-positive rate on real Claude Code sessions (read-only).

For each Write of a data-like file with >= PROV_MIN distinct 3+ digit numbers,
replay the transcript up to that call and apply the provenance share rule.
Output counts only; no content is printed.
Usage: uv run python forensics/prov_real.py [projects_dir]
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hook  # noqa: E402


def result_text(r):
    return r if isinstance(r, str) else " ".join(x.get("text", "") for x in r or [] if isinstance(x, dict))


def scan(tp):
    seen, rows, uns = "", [], []
    with open(tp, errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            m = e.get("message") or {}
            c = m.get("content")
            if isinstance(c, str):
                if m.get("role") == "user":
                    seen += "\n" + c
                continue
            for b in c or []:
                if not isinstance(b, dict):
                    continue
                t = b.get("type")
                if t == "tool_result":
                    seen += "\n" + result_text(b.get("content"))
                elif t == "text" and m.get("role") == "user":
                    seen += "\n" + b.get("text", "")
                elif t == "tool_use" and b.get("name") in ("Write", "Edit", "MultiEdit"):
                    ti = b.get("input") or {}
                    p = (ti.get("file_path") or "").lower()
                    if p.endswith(hook.DATA_EXT):
                        mine = hook.num_set(hook.edited_text(ti))
                        txt = hook.edited_text(ti)
                        if len(mine) < hook.PROV_MIN:
                            if len(hook.ANY_NUM.findall(txt)) >= hook.UNS_MIN:
                                uns.append(hook.unsourced(txt, seen))
                        elif len(mine) >= hook.PROV_MIN:
                            s = hook.num_set(seen)
                            rows.append((p, len(mine), len(mine & s) / len(mine)))
    return rows, uns


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.claude/projects")
    files = glob.glob(os.path.join(root, "*", "*.jsonl"))
    rows, uns = [], []
    for tp in files:
        r, u = scan(tp)
        rows += r
        uns += u
    trips = [r for r in rows if r[2] < hook.PROV_SEEN]
    print("transcripts %d, qualifying data writes %d, provenance trips %d (%.1f%%)" % (
        len(files), len(rows), len(trips), 100 * len(trips) / max(1, len(rows))))
    print("low-digit data writes (>= %d numbers) %d, unsourced trips %d (%.1f%%)" % (
        hook.UNS_MIN, len(uns), sum(uns), 100 * sum(uns) / max(1, len(uns))))
    for p, n, s in trips[:15]:
        print("  trip: %s n=%d seen=%.2f" % (os.path.basename(p), n, s))


if __name__ == "__main__":
    main()
