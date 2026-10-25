---
description: 'Run a mistake-tolerant task on the free proxy in a throwaway worktree; keep it only if tests pass'
argument-hint: '"<prompt>" --test "<cmd>" [--merge]'
allowed-tools: Bash(python3:*)
---
Run this with the Bash tool from the repo root, with a 30-minute timeout:

```
python3 "${CLAUDE_PLUGIN_ROOT}/worktree/wt.py" fcc $ARGUMENTS
```

Proxy URL comes from FCC_BASE_URL (default http://localhost:8082).
