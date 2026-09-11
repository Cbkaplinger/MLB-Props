# Golden Metrics — canonical definitions, sources, current values

Single contract for every number cited anywhere (backlog, paper, reports,
alerts). Updated 2026-09-11. y = actual outcome (1{K>line} or settled PnL).
“Book” = devigged consensus (paid morning/close), never raw implied.

## A. Model metrics (probabilities vs actuals)

| Metric | Definition | Source (recompute forbidden — cite) | Current |
|---|---|---|---|
| MAE_K | mean|xK − K| on graded projection dates | projection grade (`mae_K_mean_over_dates`) | 1.78 (target ≤1.75 KSplit) |
| Brier | mean(p−y)², same subset always (SOP §8) | `rescore_cal_report.json` pooled | live 0.2204 / book 0.2162 |
| Brier skill | book − ours, same subset | same | −0.0043 universe; −0.0021 bet sets |
| LogLoss | `scoring_metrics` in `prob_calibration.py` | computed, not yet tracked — do not cite a value | — |
| ECE | Σ\|acc−conf\|×weight, 10 equal bins | same report | 0.021 / 0.009 |
| MCE | max bin gap | same report | 0.088 / 0.019 |
| bias_pp | 100×mean(p−y) | same report | −1.97 / −0.32 |

## B. Quant metrics (money-track, deduped, juiced)

| Metric | Definition | Source | Current full / veto |
|---|---|---|---|
| ROI / WR | pnl/stake, win fraction, flat $50 paper | `paper_quant_report.json` | +2.7%/0.498 → +6.5%/0.512 |
| Sharpe | daily-pnl mean/std × √162 | same | 1.00 → 1.92 |
| Sharpe decay | trailing-30d Sharpe minus full-sample (SPEC — not yet computed) | TODO `paper_quant_track.py` | — |
| Sortino | downside-dev version | same | 2.08 → 4.54 |
| maxDD / currentDD | units, peak-to-trough | same + brake report | 25.8/11.1 → 20.5/1.9 |
| Calmar_u | profit_u / max_dd_u | same | 0.47 → 1.25 |

## C. Betting metrics (decision vs market)

| Metric | Definition | Source | Current |
|---|---|---|---|
| CLV | canonical close−bet, devigged pairs, pp (SOP §8 sign rule) | ledger `clv_pp`; paid `clv_paid_*_pp` | live +0.2pp-scale; paid close +0.26 / morning +0.21 |
| xCLV | model-minus-close ("model edge vs close"), pp | `decision_grade_report.json` | +8.5 judge |
| xROI | mean taken edge at decision | same | 0.170 judge |
| beat-close rate | P(CLV>0) | weekly pack | veto 0.432 (n=37) |

## D. Uncertainty + A/B (our version of industry practice)

- Bootstrap CIs: weekly pack ROI lanes + live CLV (`grade_odds_ledger --status`).
  Never cite a lane ROI without its CI.
- Min-n: 200 for cells, 30 for segments, 100+5 rule for BET-set claims.
- A/B = parallel ledgers (status-quo vs veto vs asym, weekly pack) + shadow
  arms (stacker/cap/offsets, never touching live). Champion select/judge
  discipline (#87): select 2025 once, judge 2026 once.
- Walk-forward + calibration + fractional Kelly + floor-as-threshold are our
  standing equivalents of CV gating / Sharpe-thresholds. GARCH explicitly
  rejected (program disregard list). VaR not modeled — brake + flat stakes
  cover the risk job; inverse-vol sizing not used.

## E. Cadence

Daily: board/alert/ledger. Post-settle: weekly pack, quant track, brake.
Per-coverage: closeout → paid clocks → gates. October: full re-judge.

Replay research (frozen model, juiced prices, vendor timestamps): spec
`docs/reference/oddsapi_replay_architecture.md`. Do not treat that file
as a queue.

## F. Juiced replay ledger (frozen `p_ours_cal`, 2025+2026)

Source: `artifacts/odds_log/juiced_replay_report.json` (cite, do not recompute).
Fills unmodeled. 2026 is confirmatory — not a live-policy input.

| Slice | n | ROI | WR | mean CLV pp |
|---|---:|---:|---:|---:|
| All-books flat 1u ($50) | 2077 | +7.3% | 0.506 | +1.08 |
| DK+FD-only flat 1u | 982 | +12.3% | 0.580 | +1.37 |
| 2025 flat (selection year) | 1308 | +4.2% | 0.487 | +0.95 |
| 2026 flat (confirmatory) | 769 | +12.6% | 0.540 | +1.30 |
| 1/16-Kelly (all books) | 2077 | +6.6% | 0.506 | +1.08 |

Sizing did not beat flat on ROI. BetRivers next-book soak (n=1,001, ROI +2.3%,
WR 0.429) is why all-books < DK+FD. Do not promote from 2026.
