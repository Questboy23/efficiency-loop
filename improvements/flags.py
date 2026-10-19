#!/usr/bin/env python3
"""Three cheap harness improvements behind environment flags, one hook entry point.

Usage (set by hooks/hooks.json): flags.py pre | post | stop. Reads the hook JSON on stdin.
Every mode is a silent no-op unless its flag is set to 1:
  EFFICIENCY_LOOP_CHECKLIST=1       pre:  deny Write/Edit/MultiEdit on any file but CHECKLIST.md until CHECKLIST.md exists in the project
  EFFICIENCY_LOOP_PROGRESS_METER=1  post: after 12 tool calls with no file edit, nudge once per stall (exit 2 with a message)
  EFFICIENCY_LOOP_FRESH_REVIEWER=1  stop: block the first stop of a session and ask for a fresh reviewer agent; the second stop passes
State lives in the system temp dir, keyed by session id. Nothing is sent anywhere.
"""
import json
import os
import sys
import tempfile

STALL_LIMIT = 12
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def flag(name):
    return os.environ.get("EFFICIENCY_LOOP_" + name, "0") == "1"


def state_path(data, kind):
    sid = str(data.get("session_id") or "nosession").replace("/", "_")
    return os.path.join(tempfile.gettempdir(), "efficiency_loop_%s_%s.json" % (kind, sid))


def load_state(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return {}


def pre(data):
    if not flag("CHECKLIST") or data.get("tool_name") not in EDIT_TOOLS:
        return 0
    cwd = data.get("cwd") or os.getcwd()
    target = (data.get("tool_input") or {}).get("file_path", "")
    if os.path.basename(target) == "CHECKLIST.md" or os.path.exists(os.path.join(cwd, "CHECKLIST.md")):
        return 0
    sys.stderr.write("Write CHECKLIST.md first: every requirement in the request, numbered, one line each, "
                     "including implied ones such as 'existing tests still pass'. Then continue.\n")
    return 2


def post(data):
    if not flag("PROGRESS_METER"):
        return 0
    path = state_path(data, "progress")
    st = load_state(path)
    if data.get("tool_name") in EDIT_TOOLS:
        st = {"calls": 0, "nudged": False}
    else:
        st["calls"] = st.get("calls", 0) + 1
    msg = None
    if st["calls"] >= STALL_LIMIT and not st.get("nudged"):
        st["nudged"] = True
        msg = ("Progress meter: %d tool calls since the last file edit. Stop exploring. State in one line what is blocking "
               "you, then make the smallest edit that tests your hypothesis." % st["calls"])
    json.dump(st, open(path, "w"))
    if msg:
        sys.stderr.write(msg + "\n")
        return 2
    return 0


def stop(data):
    if not flag("FRESH_REVIEWER"):
        return 0
    path = state_path(data, "review")
    if load_state(path).get("asked"):
        return 0
    json.dump({"asked": True}, open(path, "w"))
    sys.stderr.write("Before finishing: spawn one fresh reviewer agent. Give it only the original request, CHECKLIST.md and "
                     "the diff. Ask it to verify each requirement and to name any it cannot confirm. Fix what it finds, then stop.\n")
    return 2


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    return {"pre": pre, "post": post, "stop": stop}.get(mode, lambda d: 0)(data)


if __name__ == "__main__":
    sys.exit(main())
