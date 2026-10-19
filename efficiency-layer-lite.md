# Efficiency layer v2 (lite)

Rules for this task. Skip any rule that does not fit a small task.

- Small task (one file, under 20 lines): no CHECKLIST.md, no reviewer subagent. Edit, run the tests, finish.
- Larger task: write CHECKLIST.md with every requirement, one line each, including "existing tests still pass".
- Grep or glob before opening whole files. Script repeated edits. Prefer deleting code over adding it.
- Never edit or weaken tests to make them pass.
- Before each bug-fix attempt write "Hypothesis: ...". After two failed attempts on the same hypothesis, drop it and restart from the requirements.
- Finish by running the tests, then one line on what changed and "Confidence the tests pass: NN%".
