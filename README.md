# Efficiency Loop Harness

This repository contains the efficiency harness for Claude Code, including the forensics tripwire module and the efficiency layer skill.

## Installation

To install the harness as a Claude Code plugin:

1. Clone this repository to your local machine.
2. Ensure you have Claude Code installed.
3. Run the following command from the repository root:

   ```bash
   claude plugin install .
   ```

4. The plugin will be installed and active for all Claude Code sessions.

## Components

- **Forensics Tripwire (`forensics/check.py`)**: Detects fabricated or hand-typed data in files.
- **Efficiency Layer Skill (`skills/efficiency-layer/SKILL.md`)**: Provides rules for efficient task completion.
- **Hooks**: The forensics tripwire is automatically invoked on file write/edit operations.

## Usage

Once installed, the forensics tripwire will run automatically when you write or edit files (CSV, TSV, JSON, Markdown, or plain text). If it detects potential fabrication, it will print a warning and exit with a non-zero code, which Claude Code will handle appropriately.

For more information, see the documentation in the `forensics/` and `skills/` directories.