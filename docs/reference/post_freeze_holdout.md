# Post-freeze holdout protocol

**Freeze lock:** 2026-07-28 (LightGBM `lightgbm_krate_20260728_033241`,  
TBF `tbf_pa_ridge_workload_context_bullpen_20260728_035607`)  
**Runner:** `production/post_freeze_holdout.py`  
**Artifacts:** `artifacts/holdout/post_freeze/`

## Why this exists

Chronological 2023–2024 test metrics in the manuscript are **not** a pristine
final holdout: 2025 was consulted during earlier baseline work, and feature
selection used nested 2023–2024 folds. After locking the 180-feature stack on
2026-07-28, new games must be scored **without** reopening registries.

## Partitions

| Name | Definition | How to read |
|---|---|---|
| `post_freeze` | `game_date >= 2026-07-28` | **True** post-lock monitoring (grows daily) |
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

Manuscript chrono test (2024-08-06+) was k_rate MAE ≈ 0.0787 / expected_K ≈ 1.79 — 2026 YTD is in the same ballpark on the historical-feature path.

Re-run after each daily refresh so `post_freeze` accumulates real post-lock games.

## Daily logged projections (separate from holdout)

Formal expected_K logging started **2026-07-28** (`artifacts/projection_log/`).
There is **no** logged slate for 2026-07-27 in the projection log.

```powershell
python production/log_projections.py --allow-stale   # today
# After Savant + Level 1 include that date's finals:
python production/grade_projections.py --preferred-only
python production/grade_projections.py --all-logged --preferred-only
```

`post_freeze` holdout uses Level 3 historical lineup proxies; graded logs use
**announced** RG lineups from the live path. See `docs/reference/lineup_train_serve.md`.
