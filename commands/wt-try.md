---
description: 'Hypothesis sandbox: apply a change in a worktree, keep it only if a benchmark number improves'
argument-hint: '"<change to try>" --bench "<cmd printing a number>" [--lower-better] [--merge]'
allowed-tools: Bash(python3:*)
---
Run this with the Bash tool from the repo root, with a 30-minute timeout:

```
python3 "${CLAUDE_PLUGIN_ROOT}/worktree/wt.py" try $ARGUMENTS
```

The last number the bench command prints is the metric. Default arm is fcc.
