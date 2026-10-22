# PROPOSAL — calibration + feature selection for the top 2 markets
# (pregame-pa-ext-v2 lane, 2026-10-22; owner task 3)

Target markets (from sportsbook_market_inventory_2026-10-22.md, by
data volume): **pitcher_strikeouts** (principal + alternate ladder)
and **pitcher_hits_allowed**. Both have timestamped open/close quotes
for 13/8 books across 2023-05..2026-10. This is a PROPOSAL (design
only; no code, no data touched). Nested CV and feature work run on
development data only; confirm_2025H2 stays held out until the final
check.

## 1. Prediction targets and generators

| market | target | generator (existing, no new family) |
| --- | --- | --- |
| pitcher_strikeouts | P(K = k) per start | the registered count layer (M0 v2 descriptive arm proved the machinery exact; C-B1 closed) |
| pitcher_hits_allowed | P(H = k) per start | M0's P(class 3 = hit) per PA aggregated over the registered BF workload (same Binomial mixture machinery) |

Per-market calibration THEN evaluation; never refit on evaluation data.

## 2. Benchmark hierarchy (beating the close is the bar)

- **Closing line** (de-vigged per book, consensus across books at the
  `close` snapshot): the benchmark to beat for any claimed edge.
- **Opening line** (`open18` / `morning` snapshot): diagnostic only -
  does the model find value BEFORE the market moves (CLV vs open).
- Report per market: log loss and Brier vs close-implied probability,
  reliability by probability bucket, and CLV (fill price vs close).

## 3. Calibration plan (per market, honest by construction)

1. Split dev time-wise into calibration folds by BLOCK (2024H2,
   2025H1), never random: fit on 2023..block-start, calibrate on the
   block, matching the frozen recipe's CAL convention.
2. Per-market reliability: bucket model probabilities (deciles),
   report observed frequency, per-bucket log loss contribution; flag
   monotonicity violations.
3. Refit gating: a calibration adjustment (temperature/Platt per
   market) is adopted ONLY if held-out log loss improves on the NEXT
   block (walk-forward), else the previous calibration stands.
4. The confirmation block receives the FINAL frozen calibration once;
   results reported separately, no retuning.

## 4. Feature-selection plan (nested, time-ordered, grouped)

1. **Nested time-ordered CV:** outer walk-forward blocks (fit 2023 ->
   eval 2024H2; fit 2023..2024H2 -> eval 2025H1). Inner loop: within
   each outer fit window, a time-ordered inner split (last 60 days =
   inner validation, mirroring the frozen CAL convention). NO random
   splits anywhere.
2. **Group add/drop** (never one-at-a-time): pitcher form
   (n_prior, ew_pitcher), batter form (n_prior, ew_batter), park,
   lineup-context (the 8 FEAT_H3 features define the base groups; any
   NEW feature must state its group). A group enters only if inner-
   validation multiclass log loss improves; leaves only if removal
   does not hurt. One multinomial fit scores every set (one proper
   score across all four outcomes; the classes share PAs).
3. **Freeze:** the chosen feature set + windows + calibration are
   frozen BEFORE the confirmation block is touched; the frozen set is
   recorded in a card before any confirmation use.
4. **Reporting:** dev result (walk-forward) and confirmation result
   reported separately, never pooled.

## 5. Metrics matched to targets

- K counts / hits counts (ordered): RPS (registered vocabulary) plus
  per-line log loss/Brier at the principal and alternate lines.
- Over/under at a specific line: log loss / Brier against the close-
  implied probability (de-vigged), per book and consensus.
- MAE/RMSE only as coarse point-prediction context, never as the
  decision metric.
- Model-vs-close comparisons use the SAME 4,823-start dev population
  (coverage join documented in odds-coverage-v1), identical keys both
  sides, abstentions excluded as registered.

## 6. Explicitly out of scope until gated

- No live/production change, no Kelly/floor/policy edits, no new
  gates beyond the frozen contracts, no confirmation-block access
  before the final check.
