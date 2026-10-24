---
description: 'Run a long job (backtest, benchmark) inside a worktree in the background'
argument-hint: '<name> -- <command...>'
allowed-tools: Bash(python3:*)
---
Run this with the Bash tool from the repo root, with a 30-minute timeout:

```
python3 "${CLAUDE_PLUGIN_ROOT}/worktree/wt.py" bg $ARGUMENTS
```

Report the pid and log path.
