---
description: 'Best-of-N: N agents in separate worktrees on one prompt, keep the winner'
argument-hint: '"<prompt>" [-n 3] [--test "<cmd>"] [--fcc|--harness] [--merge]'
allowed-tools: Bash(python3:*)
---
Run this with the Bash tool from the repo root, with a 30-minute timeout:

```
python3 "${CLAUDE_PLUGIN_ROOT}/worktree/wt.py" tourney $ARGUMENTS
```

Report the table and the winner. Without --test, the winner is the run with the fewest tokens. Cost is about N times one run.
