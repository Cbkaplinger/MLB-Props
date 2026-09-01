# Weekly policy settle pack

**Generated:** 2026-09-01T18:44:14Z  
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
| `status_quo_king_floor` | 74 | -0.0155 | 0.4865 | 0.5862 | 45/29 |
| `veto_4_5_over` | 56 | 0.0825 | 0.5357 | 0.5 | 27/29 |
| `veto_2_5_over` | 70 | 0.0335 | 0.5143 | 0.5862 | 41/29 |
| `probation_skip_2_5_3_5_over` | 53 | 0.0669 | 0.5283 | 0.5909 | 24/29 |
| `veto_low_line_overs_le4_5` | 35 | 0.2563 | 0.6286 | 0.4615 | 6/29 |
| `asym_over16_under12` | 58 | 0.1056 | 0.569 | 0.6154 | 20/38 |
| `asym16_plus_veto_4_5` | 53 | 0.1399 | 0.5849 | 0.5455 | 15/38 |

## Block-bootstrap ROI (by game_date)

| Lane | blocks | p2.5 | p50 | p97.5 |
| --- | ---: | ---: | ---: | ---: |
| `status_quo_king_floor` | 9 | -0.233 | -0.0281 | 0.2272 |
| `veto_4_5_over` | 9 | -0.2015 | 0.076 | 0.4297 |
| `asym16_plus_veto_4_5` | 9 | -0.0652 | 0.1397 | 0.3473 |
| `veto_low_line_overs_le4_5` | 9 | -0.1788 | 0.2623 | 0.6149 |

## Status-quo line × side

| Line | Side | n | ROI | WR |
| ---: | --- | ---: | ---: | ---: |
| 2.5 | over | 4 | -1.0 | 0.0 |
| 3.5 | over | 17 | -0.0594 | 0.4706 |
| 3.5 | under | 3 | 0.656 | 0.6667 |
| 4.5 | over | 18 | -0.4086 | 0.3333 |
| 4.5 | under | 10 | 0.4001 | 0.7 |
| 5.5 | over | 4 | -0.07 | 0.5 |
| 5.5 | under | 7 | 0.476 | 0.7143 |
| 6.5 | over | 2 | 0.2466 | 0.5 |
| 6.5 | under | 4 | -0.1222 | 0.5 |
| 7.5 | under | 2 | 0.0177 | 0.5 |
| 8.5 | under | 3 | 0.2639 | 0.6667 |

## Brier skill vs market (status quo)
- All: `{'available': True, 'n': 74, 'brier_model': 0.27926, 'brier_market': 0.25099, 'brier_skill_vs_market': -0.11262}`
- Over: `{'available': True, 'n': 45, 'brier_model': 0.32246, 'brier_market': 0.25221, 'brier_skill_vs_market': -0.27854}`
- Under: `{'available': True, 'n': 29, 'brier_model': 0.21223, 'brier_market': 0.2491, 'brier_skill_vs_market': 0.14804}`

## Reproduce
```bash
python production/ops/run_weekly_policy_settle_pack.py
```

Artifacts: `artifacts/odds_log/weekly_policy_settle_pack_latest.json`, `artifacts/odds_log/weekly_policy_parallel_ledgers.parquet`.
