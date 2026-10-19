---
name: efficiency-layer
description: Working rules for coding tasks that cut wasted turns and tokens: intake checklist, search before reading, verify before claiming done. Use at the start of any multi-step coding task.
---

# Efficiency layer v1

These are working rules for this task. They exist so the task finishes correctly with less wasted work.

## 1. Intake (before any edits)
- Write CHECKLIST.md: every requirement in the request, numbered, one line each. Include implied requirements, such as "existing tests still pass" and "no unrelated changes."
- Rate the stakes as low, medium, or high. Low: start immediately. High: write a 3-line plan first.
- If a much smaller change would deliver nearly everything requested, note that in one line, then do the requested version.

## 2. Working efficiently
- Search (grep, glob) before opening whole files, and open only what the task needs.
- For the same edit in many places, write a script instead of editing by hand.
- When deleting or simplifying code solves the task as well as adding code, prefer deleting or simplifying.
- Delegate broad codebase searches to a subagent to keep the main context small. Do not spawn a subagent for anything smaller than the cost of briefing it.
- Never edit or weaken tests to make them pass.

## 3. Hypotheses and stalls
- Before investigating a bug, list 3 possible causes, not 1.
- Before each fix attempt, write one line: "Hypothesis: ..."
- Stall rule: once two attempts based on the same hypothesis fail, that hypothesis is banned. Then work through these in order:
  1. Zoom out: write the concrete symptom, the general class of problem it belongs to, and the principle that governs that class.
  2. Reframe: How would this be done with a tenth of the code or tokens? What would guarantee failure? Can removing code solve it?
  3. Restart from CHECKLIST.md as if seeing the task for the first time.
- At each stall, answer: "Would I start this approach today, knowing what I know now?" If not, switch approaches.

## 4. Pulse check
- After roughly every 10 tool calls, do one short check: re-read CHECKLIST.md, look at the latest test output, and state which requirements are done.
- If nothing new is done since the last pulse, apply the stall rule.
- Every self-check must cite evidence: test output, the checklist, or the diff. Do not change working code based on self-critique alone.

## 5. Verification before finishing
- Run the tests.
- Spawn a fresh reviewer subagent. Give it only the original request, CHECKLIST.md, and the diff or changed files. Do not give it your reasoning. Ask it to mark each requirement met or unmet and to report any bug with a concrete failing input.
- Fix unmet items, with at most 2 review rounds.
- End with "Confidence the tests pass on a clean checkout: NN%" and a one-line summary of what changed.

## 6. 10x review (capped)
- When: once before the first edit on medium or high stakes tasks, and once after the first version that passes the tests. Skip both on low stakes tasks.
- How: in at most 150 words, answer "How could this be done 10x better or 10x cheaper, not 10% better?" List at most 2 ideas.
- Adopt an idea only if switching to it costs less than finishing the current approach. Otherwise note it in one line and continue.
- Do not repeat the 10x review on the same task beyond these two points.
