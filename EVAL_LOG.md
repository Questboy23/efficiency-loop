# Eval log (append only)

| date | metric | value | previous | data | note |
|---|---|---|---|---|---|
| 2026-10-18 | forensics real-file false-positive rate | 9/136 = 6.6% | 60% (3/5, first version) | real CSVs on this machine, tuned on same files | above 5% target, not held out |
| 2026-10-18 | polyglot pass, layer_improved vs baseline | 20/20 vs 20/20 | none | 20 seeded tasks, 1 run | ceiling; +75.6% tokens, 46.7 s vs 18.6 s median wall; 20 runs served partly by claude-opus-5-5 (reviewer subagent) |
| 2026-10-18 | forensics bench, fabricated runs | 2 baseline, 2 forensics, 0 hook trips | none | 10 tasks, 1 run | hook caught nothing |

Decision: the three flags stay off by default. layer_improved costs 75.6% more tokens with no pass-rate gain on this task set, so it is not recommended until a harder task set shows a benefit.
Next loop target: forensics false positives (weakest metric), measured on a frozen held-out file list.
| 2026-10-18 | forensics FP, frozen split (forensics/heldout.py, md5(path) odd = held-out) | held-out 6/85 = 7.1%, dev 0/99 | held-out 8/85 = 9.4%, dev 1/99 | 184 real CSVs on this machine | Benford+last-digit pair now needs first-digit MAD >= 0.05; synthetic detection 219/220 (was 220/220), synthetic FP 0/100 per shape set. Still above 5% target; held-out trips not inspected per file, only counted by test (benford/last-digit dominate). Kept.
| 2026-10-18 | forensics detection, ordering_violation (OHLC, min/mean/max) | ohlc fabricated 20/20, synthetic real OHLC FP 0/100 | none (no detector) | gen.fab_ohlc / gen.real_ohlc_csv, seeds 1-100; real-file split unchanged: dev 0/99, held-out 6/85 | New detector, regression test in FabricatedTrip. Held-out FP not improved (7.1%), no regression. Kept. Python run via `uv run python forensics/bench.py`. |
| 2026-10-18 | forensics detection, cyclic_values (Likert-style column repeating a fixed cycle) | survey fabricated 20/20, synthetic real survey FP 0/100; overall detection 259/260 | none (no detector) | gen.fab_cycle / gen.real_survey_csv; real-file split: dev 0/99, held-out 6/85 | First version tripped 1 dev file (crypto-quant cost_mult parameter grid, dev 0->1). Fix: skip when another low-cardinality column holds in runs (nested sweep). Held-out FP unchanged at 7.1%, no regression. Kept. Commands: uv run python forensics/bench.py, uv run python forensics/heldout.py |
