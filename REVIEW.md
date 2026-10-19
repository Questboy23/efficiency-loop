# Review of current work (17:30). Fix these before moving on.

1. forensics/check.py: 4 of 9 tests are stubs that return None (GRIM, impossible values, internal arithmetic, too-perfect patterns). A stub that silently passes is worse than no test. Implement them.
2. The extractor flattens everything into one list of numbers, so row, column and header structure is lost. That is why the stubs say "no context". Parse CSV/TSV/Markdown tables into columns with headers first. Then: impossible values use header names (p, prob, %, sd, count, n); GRIM uses a mean column plus an n column; internal arithmetic checks rows/columns labeled total or sum; too-perfect checks p-value columns and constant differences down a column.
3. Run Benford per column, not across a whole file of mixed columns (mixing columns produces false alarms).
4. The plugin layout is wrong. In Claude Code plugins, only plugin.json lives inside .claude-plugin/. skills/ and hooks/ go at the plugin root, and hooks are declared in hooks/hooks.json using Claude Code's hook schema: {"hooks": {"PostToolUse": [{"matcher": "Write|Edit|MultiEdit", "hooks": [{"type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/forensics/hook.py"}]}]}}. The hook receives JSON on stdin with tool_input.file_path; write forensics/hook.py to read it, skip non-data files, and exit 2 with the message on stderr when it trips. Then run `claude plugin validate .`.
5. tests: there is only test_extractor.py, and unittest discovery fails because forensics/tests has no __init__.py. Add tests for every check, real vs fabricated, and make `python3 -m unittest discover -s forensics/tests -t .` pass.
6. Commit after each numbered item.

## Added 18:20
7. RESULTS.md shows a 60% false-positive rate (3 of 5 real files tripped). Target: under 5% on real data, measured on at least 20 real files (use every CSV under ~/hospitalprice/out/tables and ~/housing_forecast/results, read-only). Per-column testing and Holm correction should fix most of it. Do not tune thresholds on the same files you report; split them.
8. RESULTS.md is written with literal "\n" characters instead of newlines. Fix bench/report.py.
9. The staged files are not committed. Commit them now, then keep committing after each item.
