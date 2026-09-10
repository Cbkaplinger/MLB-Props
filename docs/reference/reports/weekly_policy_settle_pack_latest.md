# Weekly policy settle pack

**Generated:** 2026-09-10T01:26:02Z  
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
| `status_quo_king_floor` | 120 | 0.0345 | 0.5083 | 0.4898 | 72/48 |
| `veto_4_5_over` | 91 | 0.0957 | 0.5385 | 0.4444 | 43/48 |
| `veto_2_5_over` | 114 | 0.0517 | 0.5263 | 0.4792 | 66/48 |
| `probation_skip_2_5_3_5_over` | 88 | 0.0569 | 0.5341 | 0.4865 | 40/48 |
| `veto_low_line_overs_le4_5` | 59 | 0.1643 | 0.5932 | 0.4167 | 11/48 |
| `asym_over16_under12` | 102 | 0.1729 | 0.6078 | 0.5517 | 34/68 |
| `asym16_plus_veto_4_5` | 92 | 0.2101 | 0.6304 | 0.52 | 24/68 |

## Block-bootstrap ROI (by game_date)

| Lane | blocks | p2.5 | p50 | p97.5 |
| --- | ---: | ---: | ---: | ---: |
| `status_quo_king_floor` | 15 | -0.1494 | 0.0335 | 0.2153 |
| `veto_4_5_over` | 15 | -0.1132 | 0.0917 | 0.3313 |
| `asym16_plus_veto_4_5` | 15 | 0.0595 | 0.2107 | 0.3603 |
| `veto_low_line_overs_le4_5` | 15 | -0.1168 | 0.1635 | 0.4239 |

## Status-quo line × side

| Line | Side | n | ROI | WR |
| ---: | --- | ---: | ---: | ---: |
| 1.5 | over | 1 | -1.0 | 0.0 |
| 2.5 | over | 6 | -0.2051 | 0.1667 |
| 3.5 | over | 26 | 0.0358 | 0.5 |
| 3.5 | under | 3 | 0.656 | 0.6667 |
| 4.5 | over | 29 | -0.1973 | 0.4138 |
| 4.5 | under | 14 | 0.238 | 0.6429 |
| 5.5 | over | 6 | 0.1473 | 0.5 |
| 5.5 | under | 10 | 0.5573 | 0.7 |
| 6.5 | over | 4 | 0.5423 | 0.75 |
| 6.5 | under | 9 | -0.3389 | 0.3333 |
| 7.5 | under | 7 | 0.0401 | 0.5714 |
| 8.5 | under | 5 | 0.4576 | 0.8 |

## Brier skill vs market (status quo)
- All: `{'available': True, 'n': 120, 'brier_model': 0.27193, 'brier_market': 0.25147, 'brier_skill_vs_market': -0.08136}`
- Over: `{'available': True, 'n': 72, 'brier_model': 0.29816, 'brier_market': 0.25253, 'brier_skill_vs_market': -0.18069}`
- Under: `{'available': True, 'n': 48, 'brier_model': 0.23258, 'brier_market': 0.24988, 'brier_skill_vs_market': 0.06922}`

## Reproduce
```bash
python production/ops/run_weekly_policy_settle_pack.py
```

Artifacts: `artifacts/odds_log/weekly_policy_settle_pack_latest.json`, `artifacts/odds_log/weekly_policy_parallel_ledgers.parquet`.
