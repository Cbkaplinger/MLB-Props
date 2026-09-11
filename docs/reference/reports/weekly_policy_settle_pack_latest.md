# Weekly policy settle pack

**Generated:** 2026-09-11T14:48:45Z  
**Window:** game_date > 2026-08-21 (post-freeze)  
**Status:** ops / shadow — does not edit live KING.

## Locked live skip plan (2026-09-01)

| Line / side | Live action | Why |
| --- | --- | --- |
| **4.5 over** | **HARD SKIP** | Clearest bleed |
| 2.5 over | Soft probation | Tiny n, red |
| 3.5 over | Soft probation | Mild red; no hard veto yet |
| 5.5 over | Watch / discretionary | All-time ugly, post-freeze thin |
| Unders (incl. 4.5 under) | Keep | Unders carrying results |
| Book-quality filter | WONT_DO | Lines usually synced |

## Policy lanes (point estimates)

| Lane | n | ROI | WR | CLV>0 | over/under |
| --- | ---: | ---: | ---: | ---: | --- |
| `status_quo_king_floor` | 125 | 0.0717 | 0.512 | 0.48 | 76/49 |
| `veto_4_5_over` | 95 | 0.1432 | 0.5474 | 0.4324 | 46/49 |
| `veto_2_5_over` | 117 | 0.0473 | 0.5214 | 0.4792 | 68/49 |
| `probation_skip_2_5_3_5_over` | 91 | 0.051 | 0.5275 | 0.4865 | 42/49 |
| `veto_low_line_overs_le4_5` | 61 | 0.1626 | 0.5902 | 0.4167 | 12/49 |
| `asym_over16_under12` | 106 | 0.2066 | 0.6132 | 0.5161 | 37/69 |
| `asym16_plus_veto_4_5` | 96 | 0.2443 | 0.6354 | 0.4815 | 27/69 |

## Block-bootstrap ROI (by game_date)

| Lane | blocks | p2.5 | p50 | p97.5 |
| --- | ---: | ---: | ---: | ---: |
| `status_quo_king_floor` | 16 | -0.1052 | 0.071 | 0.2477 |
| `veto_4_5_over` | 16 | -0.0648 | 0.1415 | 0.362 |
| `asym16_plus_veto_4_5` | 16 | 0.0889 | 0.2417 | 0.4224 |
| `veto_low_line_overs_le4_5` | 16 | -0.1001 | 0.1603 | 0.4336 |

## Status-quo line × side

| Line | Side | n | ROI | WR |
| ---: | --- | ---: | ---: | ---: |
| 1.5 | over | 1 | -1.0 | 0.0 |
| 2.5 | over | 8 | 0.2744 | 0.375 |
| 3.5 | over | 26 | 0.0358 | 0.5 |
| 3.5 | under | 3 | 0.656 | 0.6667 |
| 4.5 | over | 30 | -0.2132 | 0.4 |
| 4.5 | under | 14 | 0.238 | 0.6429 |
| 5.5 | over | 6 | 0.1473 | 0.5 |
| 5.5 | under | 10 | 0.5573 | 0.7 |
| 6.5 | over | 5 | 0.5769 | 0.8 |
| 6.5 | under | 10 | -0.367 | 0.3 |
| 7.5 | under | 7 | 0.0401 | 0.5714 |
| 8.5 | under | 5 | 0.4576 | 0.8 |

## Brier skill vs market (status quo)
- All: `{'available': True, 'n': 125, 'brier_model': 0.26708, 'brier_market': 0.25077, 'brier_skill_vs_market': -0.06504}`
- Over: `{'available': True, 'n': 76, 'brier_model': 0.28819, 'brier_market': 0.25159, 'brier_skill_vs_market': -0.14549}`
- Under: `{'available': True, 'n': 49, 'brier_model': 0.23434, 'brier_market': 0.24951, 'brier_skill_vs_market': 0.0608}`

## Reproduce
```bash
python production/ops/run_weekly_policy_settle_pack.py
```

Artifacts: `artifacts/odds_log/weekly_policy_settle_pack_latest.json`, `artifacts/odds_log/weekly_policy_parallel_ledgers.parquet`.
