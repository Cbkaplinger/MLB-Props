# K-Rate Retrain Spec (2026-09-10; backlog #58)

> Goal: a production k-rate bundle that beats closes (Brier skill ≥ 0),
> built under full discipline. Master work-state: `docs/EXECUTION_BACKLOG.md`.
> TBF ridge is OUT of scope (WS3 v1/v2/v3 killed point-modeling pre-retrain;
> marathon error is policy-side + fat tails).

## 1. Candidates (single-feature rule — leave-one-in, one at a time)

| # | Term(s) | Evidence | Status |
| --- | --- | --- | --- |
| 1a | `pitcher_age` | Per-term +0.00066/+0.00033 MAE (#59) + Brier +0.00064 (#64) | KEPT (confirmed) |
| 1b | `pitcher_age2` | Identical predictions to age alone (monotone transform — trees can't tell them apart, #59) | RETIRED as redundant |
| 1c | `age_x_whiff_gap` | MAE hair-thin (#59) but Brier +0.00107, best at 3.5/4.5/5.5 (#64) | KEPT (confirmed) |
| 1d | `age_x_velo_gap` | Per-term −0.00001/−0.00009, zero-or-worse (#59) | DROPPED |
| 3 | Workhorse (ridge-side: PA_P20/Outs/efficiency) | Already built as WS3v3 (#36: +0.009 overall, marathons worse → KILL). Spec's "unbuilt" was wrong — corrected #64. Remaining sliver (k-rate-side workhorse interaction) is thin-theoried: K error is k-rate error, workload is TBF-side | RETIRED (v3 covers it) |
| 2 | `kadj` (usage-weighted per-pitch CSW residual vs league) | Overlay +0.00096 universe (#54) but MEMBER +0.00015 (#61 KILL-narrow) and LEDGER-GATE −0.00018 (#62 KILL) — signal lives in unselected data, neither vehicle converts it to selected edge | RETIRED (diagnostic note kept: arsenal residuals are real but unexploitable here) |
| 3a–b | Workhorse terms (`PA_P20`-high flag, pitch-efficiency) | WS3v3 lesson: marathon error is MEAN shrinkage of workhorses, not mixture (#36) | Scoped, unbuilt |

RETlRED (do not nominate): `cmd_roll30` (#57 final — model absorbs it),
slot aggregates (#49, w=0.0), linear recency deltas (#25), velo cliffs (#26),
`kadj` both vehicles (#61/#62), family-vulnerability (#63 — stable inputs,
Brier-negative), post-hoc overlays of any of the above (#33 lesson: overlays poison tails).

## 2. Splits (native — no exceptions)

2023–24 train / 2025 holdout / 2026 clean. All three candidates are
computable back to 2023 (DOBs static; L2 workload/pitch-type from 2023-03-30),
so unlike command (#57) nobody needs a split exception. 2025 is holdout,
never train. 2026 is the clean verdict.

## 3. L3 implementation (leakage-safe, nulls kept)

- Age: `_join_age_features` EXISTS (nulls kept, 420/18,263 missing).
- kAdj: NEW `_join_kadj_features` — prior-20 pitch-weighted per-pitch CSW,
  expanding league priors (strictly prior dates), prior-5 usage weights,
  hard gates (≥5 starts, ≥300 pitches) else null + `kadj_missing` flag.
  (Prototype logic: `production/ops/market_research/ws8_kadj_probe.py`.)
- Workhorse: NEW cols on existing L2 (`PA_P20`-high indicator + per-PA pitch
  efficiency); nulls kept + flags per #45 missingness doctrine (never silent
  mean-fill; monitor missing-rate per slate, alarm at >2x baseline).
- L3 rebuilds must explain row-count deltas before training (audit rule).

## 4. Training discipline (per term)

- Vehicle: retrain the member(s) whose set carries the term (or a
  final58-equivalent shootout), re-blend at production weights
  (0.0 / 0.6 / 0.4), judge on universe Brier — never a member in isolation.
- Hyperparams/seeds FIXED across arms (option-A lesson: same seeds, same
  early-stopping; report best-iteration — 154-vs-87 capacity inflation
  without generalization is a fail signal, #57).
- Judging is member-vs-member or ensemble-vs-ensemble ONLY. Single-member
  retrains trail the production ensemble by ~0.013 by construction (#57) —
  that gap is ensemble value, not a feature verdict.
- Kill per term (defaults): held-out universe Brier gain ≥ 0.0005 AND
  directionally-better MAE. Surviving terms combine ONE at a time (no family
  dumps), re-judged at each step.

## 5. Promotion path (per surviving bundle)

1. Nested folds / walk-forward confirm (`phase11b_*` machinery — probes'
   single split does not promote).
2. Per-line WS1c-Platt REFIT scoped (maps are fit to bundle outputs; a new
   bundle needs new maps, chrono-gated, never live-edited).
3. Ledger-gate on the bettable panel (n≈1k) + weekly-pack confirm.
4. User sign-off + revert path (prior bundle hashed + restorable).
5. kAdj overlay shadow (`ws8` beta vehicle) gates in parallel per SOP —
   overlay and retrain are separate vehicles with separate gates.

## 6. Build order

1. Per-term age ablation (owed debt, cheapest). DONE #59+#64.
2. kAdj L3 + member test (+ ledger-gate overlay in parallel). DONE #60/#61/#62 — both vehicles dead.
3. Workhorse terms. RETIRED — v3 already built it (#36, #64 correction).
4. Combined final: base58 + age + whiffgap KILLED (#65). Base+age(59)
   cleared Brier +0.00064 (#64) but FAILED walk-forward (#66: pooled
   −0.00004, F5 −0.00145, MAE-negative all late folds). No ledger gate.
5. Fills (Novig ≥50) gate any edge claim before AND after.

## 7. Closure (2026-09-10 #66)

Pregame retrain path EXHAUSTED: every candidate with a surviving gate died
at a later one (age±, kadj, command, workhorse, slots, family-vuln).
No new member bundle; no re-sweep; no refit. The program is timing +
selection + fills + monitoring. Reopen only on: new data source in hand,
or 2026-full-season evidence review (offseason).
