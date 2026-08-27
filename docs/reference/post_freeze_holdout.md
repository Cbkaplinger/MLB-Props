# Post-freeze holdout protocol

**Active deployment lock:** `KING_PROFILE_AUG2026` (ensemble + policy profile)  
**Legacy single-model lock:** 2026-08-03 (`lightgbm_krate_20260803_155401`)  
**Runner:** `production/projections/post_freeze_holdout.py`  
**Artifacts:** `artifacts/holdout/post_freeze/`

## Why this exists

Chronological 2023–2024 test metrics in the manuscript are **not** a pristine
final holdout: 2025 was consulted during earlier baseline work, and feature
selection used nested 2023–2024 folds. After lock, new games must be scored
**without** reopening registries.

## Current deployment note (Aug 2026)

Live scoring currently uses a config-driven k-rate ensemble
(`production/ops/live_krate_ensemble.json`) with single-model fallback. This
holdout protocol remains the canonical way to evaluate post-lock drift without
re-opening feature/selection procedures.

## Partitions

| Name | Definition | How to read |
|---|---|---|
| `post_freeze` | `game_date >= 2026-08-03` | **True** post-lock monitoring (grows daily) |
| `season_2026_pre_freeze` | 2026 rows before freeze date | Live-season check; may have been seen operationally |
| `season_2025` | All 2025 `PA≥9` rows | **Reference only** — contaminated by prior peeking |

Do not promote features or retune from these partitions without a new nested
protocol.

## Latest run (2026-07-28 after L1–L3 refresh through 2026-07-27)

Frozen models scored; nothing refit.

| Partition | n | k_rate MAE | expected_K MAE | TBF MAE | note |
|---|---:|---:|---:|---:|---|
| `post_freeze` | 0 | — | — | — | No Level 3 rows on/after freeze yet (Savant through 07-27) |
| `season_2026_pre_freeze` | 3048 | 0.0781 | 1.776 | 2.538 | Live-season monitor |
| `season_2025` | 4750 | 0.0795 | 1.806 | 2.522 | Contaminated reference |

Legacy manuscript chrono references are retained in paper/research history; this
protocol is for forward post-lock drift tracking only.

Re-run after each daily refresh so `post_freeze` accumulates real post-lock games.

## Daily logged projections (separate from holdout)

Formal expected_K logging started **2026-07-28** (`artifacts/projection_log/`).
There is **no** logged slate for 2026-07-27 in the projection log.

```powershell
python production/projections/log_projections.py --allow-stale   # today
# After Savant + Level 1 include that date's finals:
python production/projections/grade_projections.py --preferred-only
python production/projections/grade_projections.py --all-logged --preferred-only
```

`post_freeze` holdout uses Level 3 historical lineup proxies; graded logs use
**announced** RG lineups from the live path. See `docs/reference/lineup_train_serve.md`.

For daily live-drift decomposition and monitoring (k-rate vs TBF error, matchup
tier concentration, and scorecard PASS/WARN flags), see
`docs/reference/results_dashboard_diagnostics.md`.
