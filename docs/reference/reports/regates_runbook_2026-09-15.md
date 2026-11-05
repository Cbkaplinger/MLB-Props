# Re-gates Runbook 2026-09-15 (shadow research, no live change)

Two new lanes built and verified this turn, plus the existing deploy-matrix
re-derive they cite. Slate caps are excluded -- another agent owns them.

## Exact commands

```powershell
# 1. Stacker ROI lane (bettable ledger panel, frozen coefs, live filter per arm)
python production/ops/market_research/stacker_roi_lane.py --help
python production/ops/market_research/stacker_roi_lane.py
# writes artifacts/odds_log/stacker_roi_report.json

# 2. Legacy re-gates at universe scale (juiced taken set + scores join)
python production/ops/market_research/legacy_regate.py --help
python production/ops/market_research/legacy_regate.py
# writes artifacts/odds_log/legacy_regate_report.json

# 3. Deploy-matrix re-derive (bettable panel, Brier per segment; pre-existing)
python production/ops/market_research/deploy_regate.py --help
python production/ops/market_research/deploy_regate.py
# writes artifacts/odds_log/deploy_regate_report.json
```

All three are read-only vs live policy: they read `kpi_policy.json`,
`line_floor_policy.json`, `line_cell_gate_2025.json` and never write them.
`--help` was verified on both new scripts before the first real run.

## What each report key means

### stacker_roi_report.json
| Key | Meaning |
| --- | --- |
| `n_panel` | Bettable rows both arms filter (981: settled ledger + 2+ close books + 2+ morning books + scores + WS1c line) |
| `base` / `stacker` | Taken-set stats per arm: `n`, `roi` (flat $50 via canonical `bet_pnl` on the taken American), `pnl`, `wr`, `mean_edge` (vs ledger two-way devig), `mean_clv_proxy_pp` (mean taken-prob minus consensus-close-fair, in pp), `reject_reasons` |
| `common_taken` | Intersection head-to-head (Brier per arm; ROI identical by construction) |
| `kill` | `SURVIVE` iff stacker ROI >= base ROI with stacker n >= 200, else `KILL` |

### legacy_regate_report.json
| Key | Meaning |
| --- | --- |
| `n_taken` / `n_taken_with_gates` | Common subset (live-taken juiced rows, 2077) and rows with joined gate fields (1955) |
| `gates.<name>.gated` | Would-block slice: ROI/n on the taken set |
| `gates.<name>.ungated` | Would-pass slice on the same subset |
| `gates.<name>.verdict` | `KEEP` (blocking helps, gated n >= 100), `DROP-data-says` (blocking hurts, gated n >= 100), `THIN-n` (gated n < 100) |
| `cells_revisit` | Taken-set ROI/n for 2.5-over/under, 3.5-under, 9.5 splits |
| `gates.deploy_matrix` | Summary of `deploy_regate_report.json` (bettable-panel Brier re-derive, not re-measured here) |

## Verified results 2026-09-15

- Stacker ROI: base n=88 ROI +10.1% vs stacker n=0 (max stacker edge 0.120
  never clears floors 0.12-0.24) -> **KILL**. The stacker hugs morning
  consensus (b2=0.81), so it shows no live-size edge.
- Legacy: matchup_block KEEP (blocked +5.5% vs passed +9.3%);
  under_long_rest KEEP (+3.4% vs +7.3%); any_long_rest KEEP (+2.0% vs +6.9%);
  low_tbf THIN-n (n=0 in taken set); cell_gate_2025 KEEP
  (drop-list -3.2% vs take-list +8.7%); deploy_matrix KEEP (5 OFF, 2 flips).
- Cells: 3.5-under still negative (n=42, -8.2%, WR 0.31); 2.5-over n=18,
  -4.9%; 9.5 remains n=1 -- no read.

## Decision table (proposal vs hold)

| Observation | Action |
| --- | --- |
| Any gate reads `DROP-data-says` with gated n >= 100 | Propose a policy-shift (remove/narrow that block) with this report attached |
| Any gate reads `THIN-n` | HOLD -- do not act; re-measure when gated n >= 100 |
| All gates read `KEEP` (current state) | HOLD -- no policy-shift proposal |
| `stacker_roi_report.kill` reads `KILL` (current state) | HOLD -- stacker stays a Brier vehicle, never a selection input |
| `stacker_roi_report.kill` reads `SURVIVE` | Propose a shadow-selection trial (still not live) with the report attached |

No live or scoring file was edited. Nothing here promotes itself.

## Appendix A -- alt-ladder probe 2026-09-15 (descriptive, no live change)

Exact commands (sibling uses the same inputs/config/join as the curve
re-run, so all rows sit on the same subsets):

```powershell
python production/ops/market_research/alt_curve_measure.py
# writes artifacts/odds_log/alt_curve_report.json (fresh re-run 2026-09-15:
# n_starts 8775, skill negative at every covered line except thin 8.5
# n=419 +0.0009 / 10.5 n=11 +0.0188, worst 9.5 -0.0097, 11.5+ zero coverage)
python production/ops/market_research/alt_ladder_probe.py --help
python production/ops/market_research/alt_ladder_probe.py
# writes artifacts/odds_log/alt_ladder_report.json
```

What each new report key means (`alt_ladder_report.json`):

| Key | Meaning |
| --- | --- |
| `main_grid_benchmark` | Pooled blind-over $50 ROI over in-grid lines 2.5-9.5 (-6.38% on $966,500 stake) -- context only, not the kill bar |
| `per_line.<L>.over` | Blind-over at the book alt close on that line's subset: `roi`, `pnl`, `wr`, `median_american`, `mean_edge_vs_vigloaded_pp` (edge vs vig-loaded implied, no devig) |
| `per_line.<L>.under` | `roi`/`pnl` null (no under alt price exists); `wr_outcome_price_free` is the under outcome rate on the same subset |
| `verdicts.over_ladder` | `KILL` -- no off-grid line has n>=100 (0.5 n=1, 1.5 n=14, 10.5 n=11, 11.5+ n=0); nothing to test vs best in-grid 9.5 (+0.43%) |
| `verdicts.under_ladder` | `KILL` -- no under alt price at any line 0.5-14.5 (over-only book); under legs unpriceable |

Kill rule (pre-registered in the script): OVER survives iff an off-grid
line with n>=100 beats the best in-grid (n>=100) blind-over ROI; UNDER
survives iff a priced under leg does the same (impossible on this book).
Ladder legs on one pitcher are near-perfectly correlated subsets, so even
a priced pocket would only reshape payout/variance, not add edge.
