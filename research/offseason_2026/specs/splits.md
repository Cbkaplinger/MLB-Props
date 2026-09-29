# Split manifest (frozen spec — audit §§X, AD)

## 2023–2024 rolling-origin (model/dev only; 2025 never in fit)

- PRIMARY A (expanding monthly, ~9 folds, full OOF for 2023-05→2024-09; Aprils
  warm-up only). SENSITIVITY B (3 multi-month blocks) + C (2023→2024 transfer).
- Exact day bounds instantiated at build from `regular_season_schedule(year)`
  min/max + L1 `game_date` min/max (not hardcoded).
- Season reset: 2024-04 trains on 2023 only; carry only park factors, league
  scalar, declared prior-season shrunk. Preprocessing fits strictly `< test_start`.
  Hyperparams frozen. No calibration fitted in base comparison. Unit = start;
  CIs game-clustered. Null doctrine kept (no debut drops; report prior≥5 +
  pitches≥300 slice). Floors/caps/veto/probation/Kelly frozen during CV.
- Nested evaluation deferred (retrain path closed; CV judges frozen config).

## 2025A / 2025B (calibration + policy)

- 2025A selects calibration + policy once. 2025B tests the selected policy
  without further changes. Boundary pre-registered at build (default: mid-season
  date split; rolling-policy-folds as sensitivity).
- 2025B n-floors binding (choice log #2): n≥200 cells, ≥30/segment, 100+5 BET
  claims; below floor → direction only.
- Choice log per selection: timestamp/cutoff/candidates-hash/metric/constraints/
  selected/rejected-top3/rationale/code+data+artifact hashes.
- Final 2025 refit touches all 2025 → its 2025 backtest is in-sample, never
  validation (choice log #1). Only the locked 2026 run judges it.

## 2026 / 2027

- 2026: one locked run of the complete 2025-frozen stack; 7 prohibitions (audit
  §AG); deviations become preregged hypotheses. Never pristine.
- 2027: prospective; log all prediction-time inputs + outputs (run-ID/rowcount/
  cutoff/checksum per OBS-1).

## Manifests (every dataset/split carries)

Source files + hashes + date range + coverage vs `regular_season_schedule` +
fold defs + cutoff dates + train/test n + cluster unit + feature registry name +
hash + allow-list diff + champion/challenger artifact hashes (never binaries).
