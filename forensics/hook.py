#!/usr/bin/env python3
"""Hook script for forensics tripwire.
Called by Claude Code's hook system on PostToolUse for Write|Edit|MultiEdit.
Expects JSON on stdin with tool_input.file_path.
"""
import json
import os
import subprocess
import sys

def main() -> None:
    # Check if forensics is disabled via environment variable
    if os.environ.get("EFFICIENCY_LOOP_FORENSICS_DISABLE"):
        # Forensics disabled; do not block the operation.
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except Exception as e:
        # If we can't parse JSON, we fail safely (do not block the operation)
        sys.exit(0)

    # Extract the file path from the tool input.
    # The structure depends on the tool, but for Write|Edit|MultiEdit,
    # the file path is at tool_input.file_path.
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path")
    if not file_path:
        # No file path, nothing to check.
        sys.exit(0)

    # Make sure the file exists (it should, but just in case).
    if not os.path.exists(file_path):
        sys.exit(0)

    # Run our forensics checker on the file.
    # We use the same python interpreter that is running this hook.
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "check.py"),
         file_path],
        capture_output=False,  # Let stdout/stderr go through to the terminal
        text=True,
    )
    # If the checker trips (exit code 2), we propagate that exit code.
    # The hook system will then show the checker's message to the user.
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()