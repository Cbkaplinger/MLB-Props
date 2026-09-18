# Metric Invariants (do not change semantics during cleanup)

- **ROI** = realized on settled, staked, deduplicated tickets: `sum(PnL)/sum(stake)`.
- **Dollar expectation** per ticket = edge × stake. No separate persisted EV
  column unless a downstream interface needs it.
- **xROI** = `sum(edge*stake)/sum(stake)`. Equals mean(edge) only under flat
  stakes. Flag any unqualified mean assuming flat stakes. Under flat $50,
  unweighted == stake-weighted; label which is reported.
- **Edge** must name model probability and market reference. Never mix raw and
  calibrated probabilities under one column name.
- **CLV** = execution metric in devigged probability space: no-vig close prob
  (ticket side) minus no-vig prob of ticket price/reference at placement.
  Headline = same-book/fillable when that is policy. Report consensus and
  cross-book separately; cross-book never headlined. Scales: live ledger
  fraction vs paid/juiced percent — label every reading; standardize going
  forward, leave history untouched.
- **Beat-close rate** = fraction eligible with CLV > 0. Ties reported
  separately or treatment defined. Denominator = valid policy-compliant closes
  only.
- **Two-way devig** = canonical multiplicative implementation unless evidence
  + tests establish otherwise.
- **xCLV retired** from live selection/promotion/staking/alerting/headlines.
  Historical refs survive only to explain a deprecated decision, labeled retired.
- **One canonical implementation each**: DNP/void, dedup, settlement status,
  ticket eligibility, close eligibility, book universe, line matching,
  timestamp policy.
- **Risk clocks**: every Sharpe/Sortino/Calmar states return unit, aggregation
  frequency, annualization factor, bankroll/denominator, date span, observation
  count. Never mix per-bet/daily/active-day/calendar-day/seasonal under one label.

## Population reconciliation

Never hard-code 460 / 485 / 844 as truth. Reconcile by artifact + code path,
as-of timestamp, season/range, selector version + take gates, book universe,
line/side scope, staked/settled/void, dedup key, close coverage, replay vs
live-fill, policy vs opportunity vs ticket. Build funnel:
raw → eligible → policy → take-gate → deduped → staked → settled-non-void →
valid-close → same-book-eligible → final. Report adds/removals per stage.
Uniqueness via canonical ticket key. Splits sum to headline.
