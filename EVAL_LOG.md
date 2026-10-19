# Eval log (append only)

| date | metric | value | previous | data | note |
|---|---|---|---|---|---|
| 2026-10-18 | forensics real-file false-positive rate | 9/136 = 6.6% | 60% (3/5, first version) | real CSVs on this machine, tuned on same files | above 5% target, not held out |
| 2026-10-18 | polyglot pass, layer_improved vs baseline | 20/20 vs 20/20 | none | 20 seeded tasks, 1 run | ceiling; +75.6% tokens, 46.7 s vs 18.6 s median wall; 20 runs served partly by claude-opus-5-5 (reviewer subagent) |
| 2026-10-18 | forensics bench, fabricated runs | 2 baseline, 2 forensics, 0 hook trips | none | 10 tasks, 1 run | hook caught nothing |

Decision: the three flags stay off by default. layer_improved costs 75.6% more tokens with no pass-rate gain on this task set, so it is not recommended until a harder task set shows a benefit.
Next loop target: forensics false positives (weakest metric), measured on a frozen held-out file list.
