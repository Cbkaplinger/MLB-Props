# Model pipeline spec — pregame-pa-ext-v2 lane (2026-10-22)

One page. Every stage from raw data to the market comparison:
file:function, inputs, outputs, frozen pins. This is the source for
the architecture diagrams. All paths relative to the worktree root
(`MLB-Props-worktrees/paext-v2`); data lives OUTSIDE git
(`C:\Users\ckaplinger\MLB-Props-Research\` lake, repo `data/`).

## Stage map

| # | stage | file:function | inputs -> outputs |
|---|---|---|---|
| 1 | Raw ingestion | repo `data/Savant-Data/regular/` (statcast_YYYY_regular.parquet); `data/dimensions/player_id_map.parquet` | vendor files -> raw PA events, id map |
| 2 | PA table | `research/.../adapter.py` via OVERNIGHT_P2_DIR build (overnight-p2 lane) | raw events -> `pa_table.parquet` (731,347 rows: game_pk, at_bat_number, batter, pitcher, game_date, y) |
| 3 | Entity state | `adapter.py:entity_daily_state`, `adapter.py:league_daily_state` | pa_table -> per-(entity, date) strictly-prior cumulative + 90d-EW state |
| 4 | Features | `adapter.py:attach_prior_features`, `build_feature_frame` (via `build_checkpoint.py`) | state frames -> FEAT_H3 (8 frozen features; W_PRIOR=150, HALF_LIFE_DAYS=90) |
| 5 | Frozen checkpoint | `build_checkpoint.py` -> `checkpoints/h3_raw_checkpoint.json` | per-block fits -> serialized verified artifact; **pin `176fb18b…`** in `freeze_pregame_pa_ext_v2.json` |
| 6 | Projected scoring | `adapter.py:run_real` (gated, MLflow) | checkpoint + projected lineups (`pregame-state-v1`) + BF workload -> `outputs/projected_pa_probs_v1.parquet` (preserved ledger; slot p_h3_raw; **ledger hash `fd1841e1…`**) |
| 7 | BF workload | `bf-workload-v1` lane | per-start BF forecast `bf_forecasts.parquet` (**`c9c2762f…`**); realized K per start `start_metrics_v2.parquet` (**`af6814ec…`**; realized_k == official starter K, label-audited 100%) |
| 8 | Count aggregation | `kcount_combiner.py:count_rps, bf_pmf_from_37`; `adapter.py:cycled_cond_mean, count_pmf_from_mixture` | per-PA probs + BF pmf37 -> 24-bucket count PMF (cap 60, tail k=23) |
| 9 | Question A exact PB | `count_aggregation_exact.py:exact_count_pmf` | p9 slots + bf_ext -> exact Poisson-Binomial mixture (research arm) |
| 10 | M0 four-class model | `m0_multiclass.py:build_training_frames, fit_multinomial, run_m0` | pa_table + event labels (22-event taxonomy, 4 classes) + ledger -> M0 eval parquet (82,817 PAs; **eval keys `c6568151…`, 4,823 starts**) |
| 11 | M0 execution | `m0_multiclass.py:main --i-accept-outcome-evaluation` | real run 2026-10-22: EP1 PASS, EP2 PASS; receipts `aca95253…`/`0d7decdf…` |
| 12 | C-B1 exposure profile | `exposure_profile.py:run_cb1_eval` | band profile vs frozen prior -> CLOSED (lost by +0.086 RPS) |
| 13 | Market join | lake `odds-coverage-v1/join_coverage.py:build_task_frames` (tested, reused unchanged) | archive quotes + envelope + bf starts -> per-start event_id/first_pitch_ts |
| 14 | Near-close + de-vig | `market_eval_k.py:select_near_close, american_to_raw, devig_over, book_margins_from_two_sided` | quotes -> per-book near-close quotes, margins, consensus |
| 15 | Market eval | `market_eval_k.py:run_market_eval_k` | model PMFs + consensus + realized -> log loss/Brier vs close, reliability, placebo, receipts |
| 16 | Ablation | `ablation_features.py` (+ tests) | feature sets x walk-forward dev blocks -> model metrics only |

## Frozen pins (do not retune from 2025H2/2026)

- Checkpoint artifact `176fb18b…` (null pin = scoring refuses);
  ledger `fd1841e1…`; BF `c9c2762f…`; realized `af6814ec…`;
  lineups `b6a1947c…`; dev start keys `618e8e75…` (4,823);
  slot keys `82592f18…` (43,407); eval PAs `c6568151…` (82,817).
- Registered aggregation: cap 60, tail bucket k=23, cycled prefix-mean
  with P_CLIP; conditional independence declared a v1 approximation.
- Gates: real-data runs require the CLI acceptance flag PLUS a
  delegated owner order (the owner reply is the record); outputs are
  write-once with initial-first chained receipts; failure records are
  preserved, never repaired in place.
- Market data (outside git): `data/Odds-Historical/theoddsapi/`
  (sha-manifested; alternate ladder is OVER-SIDE ONLY), `kalshi/`
  (2026 season only). 2024 snapshots are prior-evening lines — never
  "closes".

## Open gates

- 2026 holdout: defined, not run (frozen model only, one run, Kalshi
  ladder as the two-sided benchmark).
- Ablation (half-life 30/60/90/180, separate pitcher/batter, ew_den
  feature): selects by model metrics only.
