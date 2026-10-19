# Improvements for Efficiency Loop Harness

This file lists potential improvements to the harness, ranked by expected benefit per token (EBPT). Each improvement includes a brief description, expected effect, implementation cost, and how to test it.

## Ranked Improvements

### 1. Intake: Step-0 Checklist Enforcement
- **Description**: At the start of each task, automatically prompt the user to write a CHECKLIST.md file with numbered requirements, including implicit requirements (e.g., existing tests still pass, no unrelated changes). The harness could block further progress until the checklist is written.
- **Expected Effect**: Improves task clarity, reduces scope creep, increases success rate on complex tasks.
- **Cost**: Low (requires adding a prompt and a simple file existence check).
- **How to Test**: Measure the fraction of tasks where a checklist is written before any edits, and compare task success rates with and without the feature.

### 2. Run Monitor: Progress Rate per Token
- **Description**: Track the number of tokens consumed per unit of progress (e.g., per test passed, per requirement met). Display a running metric to help users detect inefficient loops.
- **Expected Effect**: Helps users identify when they are stuck in a loop wasting tokens, allowing early intervention.
- **Cost**: Low to Medium (requires tracking token usage and defining progress milestones).
- **How to Test**: Correlate the progress rate metric with eventual task success; users should be able to spot stalls earlier.

### 3. Verification: Fresh Reviewer Subagent (already partially implemented)
- **Description**: Before considering a task complete, spawn a fresh subagent that sees only the original prompt, CHECKLIST.md, and the diff, and asks it to verify each requirement. Use its verdict to decide if more work is needed.
- **Expected Effect**: Reduces false positives where the agent thinks it's done but missed requirements.
- **Cost**: Medium (requires spawning a subagent and parsing its output).
- **How to Test**: Measure the rate of post-submission defects found by external review with and without this feature.

### 4. Parallel Search: Uncorrelated Forks
- **Description**: When faced with a uncertain approach, fork multiple subagents with different initial prompts (e.g., different temperature, different initial hypotheses) to explore the solution space in parallel.
- **Expected Effect**: Increases chance of finding a solution when the initial approach is wrong.
- **Cost**: Medium (requires managing multiple subagents and merging results).
- **How to Test**: Measure the fraction of tasks where at least one fork finds a solution that the main agent missed.

### 5. Learning Loop: Self-Improving Overseer
- **Description**: Track the agent's own performance over time (e.g., success rate, token usage) and adjust its behavior (e.g., prompt templates, tool preferences) to improve future performance.
- **Expected Effect**: Long-term improvement in efficiency and success rate as the harness learns from its own experience.
- **Cost**: High (requires persistent storage and a learning algorithm).
- **How to Test**: Track metrics over many tasks and compare trends with and without the learning loop.

### 6. Measurement: Deflated Scores and Paired Comparisons
- **Description**: Use statistical techniques to deflate scores for multiple comparisons and run paired comparisons between harness configurations to isolate the effect of individual changes.
- **Expected Effect**: More reliable measurement of improvement impact.
- **Cost**: Low (requires adding statistical analysis to the benchmarking script).
- **How to Test**: Verify that the measurement system correctly detects known improvements in controlled experiments.

### 7. New Idea: Adaptive Token Budgeting
- **Description**: Dynamically adjust the token budget allocated to different phases (e.g., intake, exploration, verification) based on observed difficulty of the task.
- **Expected Effect**: Prevents running out of tokens in critical phases and reduces waste in easy phases.
- **Cost**: Medium (requires tracking phase budgets and reallocating).
- **How to Test**: Measure the variance in token usage across tasks and the success rate under tight token budgets.

### 8. New Idea: Smoke Test for Hallucination
- **Description**: Before committing to a solution, run a quick sanity check by asking the model to explain the solution in simple terms or to verify a known property; if the explanation is incoherent, flag for review.
- **Expected Effect**: Catches blatant hallucinations early.
- **Cost**: Low (requires an additional LLM call per checkpoint).
- **How to Test**: Measure the rate of hallucination-related failures caught by the smoke test.

## Top 3 cheap improvements, implemented behind flags

All three live in `improvements/flags.py` (one hook entry point, wired in `hooks/hooks.json`). Each mode does nothing unless its flag equals `1`. Tests: `python3 -m unittest improvements.test_flags`.

| flag | hook | behavior |
|---|---|---|
| `EFFICIENCY_LOOP_CHECKLIST=1` | PreToolUse on Write, Edit, MultiEdit | Denies edits to any file except CHECKLIST.md until CHECKLIST.md exists in the project. |
| `EFFICIENCY_LOOP_PROGRESS_METER=1` | PostToolUse on every tool | After 12 tool calls with no file edit, sends one nudge per stall (exit 2). An edit resets the count. |
| `EFFICIENCY_LOOP_FRESH_REVIEWER=1` | Stop | Blocks the first stop of a session and asks for a fresh reviewer agent. The second stop passes. |

A/B arm: `run_ab.py --arms baseline,layer,layer_improved` sets all three flags plus the forensics hook for the `layer_improved` arm. Result of that A/B: see RESULTS.md (not run unless listed there).

The progress meter is a stall detector (calls since last edit), not a tokens-per-progress rate. A real rate needs a definition of progress per task type.
