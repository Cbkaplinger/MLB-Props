# Early-Season Extension — Preregistration (frozen)

Parent: `research/offseason_2026/corrected-history-workload-prereg.md`
(unchanged; base experiment COMPLETE, no retuning, no rerun).
Status: FROZEN BEFORE EVALUATION. One diagnostic extension.

Question: does the corrected-history challenger advantage survive
early-season conditions (thin training, cold starts)?

## 1. Origins and windows (exact)

Origins: 2023-04-15 only. Evaluation: [2023-04-15, 2023-05-01]
(final date inclusive). Training: [2023-03-30, 2023-04-15) 2023
labels only — 2022 labels are NOT training inputs (training-season
policy unchanged; 2022 serves histories, fallback, and team/league
priors only, per existing approvals).

Basis: dev spec Part D names "(Opening-Day week, April 15)"; April
15 is the exact usable origin (a 2023-03-30 origin would have empty
training and is deferred as a separate cold-start characterization
requiring its own fallback rule, not smuggled in here).

Inner split, clip, and BLOCKED rules: identical frozen definitions
(<3 distinct training dates or empty side = BLOCKED lane, no
full-sample fallback). Expected satisfiable (~15 distinct training
dates); verified at runtime, not assumed.

## 2. Everything else frozen (no changes)

Target BF definition, canonical team-side identity, zero-BF
identity, spine history rules, same-game/date exclusion, 10-feature
challenger, Ridge config (grid, tie-break, clip, refit), 4 arms
(challenger / corrected trailing / train-mean / team-rate),
missingness + 2022-fallback policy, metrics, paired date-clustered
+ pitcher-sensitivity CIs (2000, seed 20261001), registered
comparisons, kill rules (baseline kill applies), slices, single-run
policy, temp/research-root output gate, failure receipts.

Oracle-gap NOT_COMPUTED (no matched ablation). Legacy rolling
trailing omitted (multi-season opens prohibited). Reference-free
run is diagnostic only.

## 3. Cold-start accounting (frozen policy, no new rules)

April has elevated debut/low-history share: spine labels,
no_prior_start_fallback counts, trailing fallback counts, and the
2022-constant fallback apply exactly as in the parent run.
Experience/debut/missing-history slices are mandatory outputs.

## 4. Code identities (frozen before scores)

Runner + tests below; manifest records all hashes at runtime.
Only delta vs parent code: `--origins` / `--final-date` CLI
overrides defaulting to the frozen Jul-Sep values (default behavior
byte-identical in effect). No feature, fit, metric, or rule change.

## 5. Stop conditions

Hash/period/population/duplicate violations, nonfinite
predictions, unformable inner split (BLOCKED, exit 1), incomplete
manifest, any 2024+ access. No tuning, no rescored retries.
