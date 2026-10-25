---
description: 'Merge a worktree branch into the current branch and remove the worktree'
argument-hint: '<name>'
allowed-tools: Bash(python3:*)
---
Run this with the Bash tool from the repo root, with a 30-minute timeout:

```
python3 "${CLAUDE_PLUGIN_ROOT}/worktree/wt.py" merge $ARGUMENTS
```


