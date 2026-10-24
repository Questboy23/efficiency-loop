---
description: 'A/B: same prompt with the efficiency-loop harness off and on, in separate worktrees'
argument-hint: '"<prompt>" --test "<cmd>" [--runs 3]'
allowed-tools: Bash(python3:*)
---
Run this with the Bash tool from the repo root, with a 30-minute timeout:

```
python3 "${CLAUDE_PLUGIN_ROOT}/worktree/wt.py" ab $ARGUMENTS
```

Report pass counts and mean tokens per arm. Results append to .wt/runs.jsonl.
