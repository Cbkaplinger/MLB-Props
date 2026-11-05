# Monthly summary 2026 — live paper vs champion replay (2026-09-17)

Point-in-time. Live plan stays in `docs/EXECUTION_BACKLOG.md`.

Sources (cite, do not recompute):
- `artifacts/odds_log/monthly_quant.json` (built 2026-09-16, `monthly_quant.py`)
- `artifacts/odds_log/champion_2026_grade.json` (n=460, PnL +$2,011.93, ROI +8.7%)
- `artifacts/odds_log/select_2025_report.json` (judge n=460, ROI +8.75%, LCB +0.16%)
- Figure: `docs/paper/figures/fig11_live_equity.png` (`make_figures.py::fig11_live_equity`)

Conventions: Sharpe_pb = per-bet mean(r)/sd(r), dimensionless, NO annualization
(monthly_quant doctrine). Daily Sharpe (golden_metrics, x sqrt(162)) given
alongside where stated. $50u. Live = settled+staked+deduped, actual stakes
(mixed Kelly/flat eras). Champion = selector-exact, flat $50.

## Live paper 2026 (money truth, mixed regimes)

| Month | n | PnL | ROI | Sharpe_pb | Sortino_pb | MaxDD(u) | ExpSharpe_pb |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-07 | 22 | $+16 | +0.9% | -0.052 | -0.072 | 7.55 | -0.052 |
| 2026-08 | 264 | $+74 | +0.4% | -0.047 | -0.065 | 20.58 | -0.048 |
| 2026-09 | 80 | $+409 | +7.0% | -0.034 | -0.047 | 7.06 | -0.045 |

Daily-Sharpe convention (sqrt-162, for the golden_metrics surface):
Jul 0.38 / 0.55 / 5.3u / Calmar 0.06; Aug 0.16 / 0.25 / 17.6u / 0.08;
Sep 3.35 / 5.83 / 5.6u / 1.47; Season 0.77 / 1.24 / 17.6u / 0.57.
Trailing-30d Sharpe 0.71 vs season 0.77 (decay -0.06, flat).

Why Sharpe_pb reads negative on green months: it is EQUAL-weighted per ticket
while ROI is STAKE-weighted. July Kelly stakes ran larger on winners
(Skenes $189 won; Lowder $106 lost), so mean(r) = -5.1% while ROI = +0.9%.
Under flat $50 the two agree by construction (see champion rows).

## Champion replay 2026 (pure policy read, flat $50)

| Month | n | PnL | ROI | Sharpe_pb | Sortino_pb | MaxDD(u) | ExpSharpe_pb |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-03 | 12 | $+394 | +65.6% | 0.811 | 1.608 | 1.00 | 0.811 |
| 2026-04 | 104 | $+441 | +8.5% | 0.090 | 0.130 | 8.94 | 0.152 |
| 2026-05 | 105 | $+779 | +14.8% | 0.158 | 0.238 | 3.15 | 0.155 |
| 2026-06 | 72 | $-265 | -7.4% | -0.076 | -0.103 | 12.96 | 0.097 |
| 2026-07 | 76 | $+401 | +10.5% | 0.109 | 0.162 | 5.00 | 0.099 |
| 2026-08 | 65 | $+382 | +11.8% | 0.122 | 0.182 | 7.33 | 0.103 |
| 2026-09 | 26 | $-120 | -9.2% | -0.099 | -0.131 | 3.43 | 0.092 |

Totals: n=460, PnL +$2,012, ROI +8.7%, WR 0.574, CLV +1.14pp (460/460),
beat 0.602. Expanding Sharpe_pb never decays below +0.09 after April.

## Findings

1. August is the live gap month (xROI 0.170 expected, ROI +0.4% banked).
   Champion replay had NO August problem (+11.8%) — the live bleed was
   pre-champion regime + Kelly stakes, not the policy.
2. September diverges the other way: live +7.0% (n=80) vs champion -9.2%
   (n=26). Both thin, different sets (live Sep mixes cap-0.20-era and
   champion-era tickets). Watch item, not a conclusion.
3. Champion numbers revised down from backlog claims: n=485 / +15.6% /
   +$3,792 (2026-09-16 entries) → disk truth n=460 / +8.7% / +$2,012,
   WR 0.574, 2026-judge LCB +0.16%. Three artifacts agree
   (select_2025_report judge, champion_2026_grade, monthly_quant sums).
   2025 selection also revised: n=505 / +11.0% / LCB +3.0%
   (was cited as n=558 / +15.5% / +8.0%). Cause: candidate-set rebuild
   after the 9/16 book-filter fix + September closeout growth. The edge is
   thinner than the backlog claims — size humility accordingly.
4. Drawdown: live per-ticket maxDD 20.58u (August); champion 12.96u (June).
   Live DD panel in Fig 11 shows the August hole and September repair.
5. Sharpe decay: none. Expanding Sharpe_pb stable (-0.045 live / +0.092
   champion); trailing-30d daily Sharpe within 0.06 of full-sample.

## Next

Paper appendix: this table + Fig 11 + regime labels (pre-champion Jul/Aug vs
champion Sep). Rebuild after September closes; October full-season re-judge
decides promotion questions, not this report.

## Addendum 2026-09-17 (full requested table — DONE)

Canonical table now lives in the paper as Table 6 (App. A.8) + Fig. 10
(`fig11_live_equity.png`), built from `monthly_quant.json` extended with WR,
CLV + beat, Calmar, active days, and bets/day. HTML + PDF re-rendered and
verified (Table 6 + fig11 present in `manuscript.html`).

Reconciliation (sums to the cent): live months 22+264+80 = 366 tickets,
$16+$74+$409 = +$499 vs `daily_grading_2026-09-15.json` YTD; champion months
sum n=460, PnL +$2,012 vs `champion_2026_grade.json` (+$2,011.93); champion
April CLV +1.60pp/beat 63% reproduces the grade file exactly (1.6016/0.6346).
Numbers are correct as of the 2026-09-16 freeze.

New reads from the full columns: champion August wins +11.8% while LOSING the
close (−0.11pp, beat 46%); champion September beats the close (69%,
+1.56pp) while LOSING −9.2% — CLV and ROI each fail alone monthly, confirming
the joint-gate contract. Live September is the mirror (ROI +7.0%, beat 41%).
Density: live 8–11 tickets per active day (Jul 2 active days; Aug 28; Sep 10);
champion 2–4 per day — selectivity is the policy working as designed.
