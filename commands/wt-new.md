---
description: 'New worktree for a parallel feature, with .env copied and its own port'
argument-hint: '<name> [--link-deps]'
allowed-tools: Bash(python3:*)
---
Run this with the Bash tool from the repo root, with a 30-minute timeout:

```
python3 "${CLAUDE_PLUGIN_ROOT}/worktree/wt.py" new $ARGUMENTS
```

Tell the user the path, then: cd into it and run claude. Merge later with /wt-merge.
