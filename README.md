# Efficiency Loop Harness

This repository contains the efficiency harness for Claude Code, including the forensics tripwire module and the efficiency layer skill.

## Installation

To install the harness as a Claude Code plugin:

1. Clone this repository to your local machine.
2. Ensure you have Claude Code installed.
3. Validate, then try it for one session without installing:

   ```bash
   claude plugin validate .
   claude --plugin-dir .
   ```

4. Disable the forensics hook with `EFFICIENCY_LOOP_FORENSICS=off`. Data never leaves the machine: `check.py` and `hook.py` are standard-library Python and make no network calls.

## Components

- **Forensics Tripwire (`forensics/check.py`)**: Detects fabricated or hand-typed data in files.
- **Efficiency Layer Skill (`skills/efficiency-layer/SKILL.md`)**: Provides rules for efficient task completion.
- **Hooks**: The forensics tripwire is automatically invoked on file write/edit operations.
- **Worktree toolkit (`worktree/wt.py`)**: Runs agents in parallel git worktrees: best-of-N tournaments, harness A/B, free-proxy runs kept only when tests pass, a keep-if-better hypothesis sandbox, parallel feature folders, and background jobs. Slash commands `/wt-tourney`, `/wt-ab`, `/wt-fcc`, `/wt-try`, `/wt-new`, `/wt-bg`, `/wt-merge`, `/wt-ls`. See `worktree/README.md`.

## Usage

Once installed, the forensics tripwire will run automatically when you write or edit files (CSV, TSV, JSON, Markdown, or plain text). If it detects potential fabrication, it will print a warning and exit with a non-zero code, which Claude Code will handle appropriately.

For more information, see the documentation in the `forensics/` and `skills/` directories.