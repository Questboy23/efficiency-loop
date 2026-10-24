# wt: parallel agents with git worktrees

A worktree is a second folder of the same repo with its own branch checked out. All worktrees share one git history. Each agent edits its own folder, so parallel agents never overwrite each other.

`wt.py` creates worktrees next to the repo at `../<repo>.wt/<name>`, on branches named `wt/<name>`.

## Commands

| Command | What it does | Slash command |
|---|---|---|
| `wt tourney "<prompt>" -n 3 --test "<cmd>"` | Runs N agents on one prompt. Keeps the passing run with the fewest tokens, deletes the rest. | `/wt-tourney` |
| `wt ab "<prompt>" --test "<cmd>" --runs 3` | Runs the prompt with this plugin off and on. Prints pass count and mean tokens per arm. | `/wt-ab` |
| `wt fcc "<prompt>" --test "<cmd>" --merge` | Runs on the free proxy. Merges if the test passes, deletes the worktree if it fails. | `/wt-fcc` |
| `wt try "<change>" --bench "<cmd>"` | Measures a number, applies the change in a worktree, measures again. Keeps it only if the number improves. | `/wt-try` |
| `wt new <name>` | Makes a worktree for a parallel feature. Copies `.env` files and assigns a port. | `/wt-new` |
| `wt bg <name> -- <cmd>` | Runs a long job (backtest, benchmark) in a worktree in the background, logging to `.wt/<name>.log`. | `/wt-bg` |
| `wt merge <name>` / `wt rm <name>` / `wt ls` | Merge and remove, remove only, list. | `/wt-merge`, `/wt-ls` |

Every agent run appends one line to `.wt/runs.jsonl`: arm, pass, tokens, diff size, wall time. `.wt/` is added to `.git/info/exclude`, so it never gets committed.

## Problems it handles

- `.env`, `.env.*`, `*.local` and `.dev.vars` files are ignored by git, so a new worktree lacks them. `wt` copies them. Add more patterns with `WT_COPY=pattern1,pattern2`.
- Two dev servers on one port collide. Each worktree gets its own port (3110, 3120, ...), exported as `PORT` in `wt bg` and written to `.wt-port`.
- `node_modules` is missing in a new worktree. `wt new --link-deps` symlinks the main checkout's copy. pnpm avoids the problem because it shares one package store.
- Parallel runs multiply token use. `tourney -n 3` costs about 3 runs. `WT_MAX_PARALLEL` (default 4) caps concurrent agents.

## Settings

| Variable | Default | Use |
|---|---|---|
| `FCC_BASE_URL` | `http://localhost:8082` | free-claude-code proxy address |
| `FCC_AUTH_TOKEN` | `freecc` | token sent to the proxy |
| `WT_BASE_PORT` | `3100` | first port is this plus 10 |
| `WT_MAX_PARALLEL` | `4` | concurrent agents |
| `WT_CLAUDE` | `claude` | agent binary (tests use a fake) |

## Notes

- The `ab` "off" arm skips `--plugin-dir`. If this plugin is also installed globally, the off arm still loads it. Disable the global install before A/B runs.
- Agents run with `--permission-mode acceptEdits`, matching `run_ab.py`.
- Tests: `python3 -m unittest worktree/tests/test_wt.py` (8 tests, fake agent, no tokens).
