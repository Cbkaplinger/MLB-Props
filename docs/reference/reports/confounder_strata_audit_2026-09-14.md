# Confounder strata audit — 2026-09-14 (dated evidence)

> Point-in-time report. Live plan lives in `docs/EXECUTION_BACKLOG.md` (Session Snapshot).
> Machine source: `artifacts/odds_log/confounder_strata_report.json` (re-runnable via
> `production/ops/market_research/confounder_strata_audit.py`).

## Question

Do our headline effects survive *within* strata? Same-subset rule (SOP §8):
an effect that dies inside strata was never real. Taken set n=2,077
(juiced replay), overall ROI +7.28%, WR 0.506.

## Verdicts

| # | Test | Verdict |
|---|---|---|
| A | Edge-band ROI within book x snap | **Survives.** 0.12–0.18 band green within DK+FD at both clocks (+18.2% open, +17.1% morning). BR morning high-edge toxic (0.18–0.24: −0.6% WR 0.37; 0.24+: −13.8% WR 0.29). Edge is not book softness or clock — except at BR mornings, which are. |
| B | Side ROI within each line cell | **Line-specific, not global.** 4.5-under +14.2% (n=475, WR 0.478 — wins pay plus-money). 3.5-under −8.2%, 8.5-under −5.3%. Side alone does not predict; side x line does. Watch: 6.5-over +26.3% (n=136, WR 0.426). |
| C | Book ROI within snap | **Book effect is real.** Morning: DK+FD +12.2% (n=195) vs BR −0.6% (n=804). Open: all books green. The softness gap opens intraday. |
| D1 | Matched morning price pairs DK+FD vs BR | **Confirmed, n=135 pairs.** Same ticket pays better at DK/FD 77.8% of the time (+0.056 decimal). BR is softer *against us*. Supports the DK+FD-only champion. |
| D2 | Paired CLV take-vs-close by book | Positive everywhere; best at DK+FD (+1.37pp, 62.3% positive). |
| E | Shuffle within (line, side), win count preserved | **Price-adverse:** observed +$7,559 vs null p50 +$15,096 (p=1.0). Wins land on the worst-paying tickets within each cell — favorite concentration (small wins, full-stake losses). Measurement verified exact (recompute == stored pnl); the finding is real, not a bug. |

## Method notes (for the next auditor)

- D-zero-pairs trap: candidates hold ONE row per ticket at the chosen book, so cross-book
  pairs cannot exist there. D1 joins `book_lines_pitcher.parquet` (morning, K market)
  via `join_keys.sorted_key` + `event_date_map`. First version returned 0 pairs by design.
- E preserves win COUNT per stratum, so it tests WHERE wins land, not WHETHER roi is real.
- 0.24+/other cells are n<=5 noise — listed, never cited.

## What this changes

Nothing live. It upgrades the DK+FD-only champion from "book-mix observation" to
"matched-pair confirmed" for the October judge, and registers 6.5-over as a watch lane.
No floor/veto/Kelly change follows from this report.
