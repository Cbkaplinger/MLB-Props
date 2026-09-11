# Odds API 2025–present replay inventory — 2026-09-11

> Point-in-time research (counts, quota, envelope diagnostics). Not a work
> queue. Standing spec: [`../oddsapi_replay_architecture.md`](../oddsapi_replay_architecture.md).
> Next actions: `docs/EXECUTION_BACKLOG.md`. Frozen production model is not
> retuned here.

**Question:** what can we actually use for a frozen-model open→close backtest
on Odds API data from 2025-present?

**Answer:** the lake is already on disk. Do not re-buy. Remaining quota
**3,722,075 / 5,000,000**. The missing piece is a **point-in-time replay
layer** over data we already paid for, not another model or another
subscription.

## 1. What we already have (use this first)

| Asset | Coverage | Role in a replay |
| --- | --- | --- |
| Frozen scores (`historical_scores_2025_2026.parquet`) | 8,775 starts, 2025-03-27→2026-09-03 | Model inputs. Do not rescore. |
| Live-config panel (`universe_panel_live.parquet`) | 71,080 line-points, Poisson+WS1c | Canonical probs. `p_ours_cal` is the frozen production stack. |
| Paid Odds API pitcher lines | 1.64M rows; K 151,862 close + 148,828 morning; 9 US books | Executable American prices + consensus. |
| Paid batter lines | 10.9M rows, parked | Future namespace only. No batter model. |
| Friend −12h/−6h opens | 26,147 K rows, 2,964 events, 2025-03-27→2026-07-10; 97% at −12h | Decision-time open for 2025 + 2026 through 7/10. Same vendor `event_id` space (2,928 overlap with paid). |
| Consensus cache | 70,337 K+outs × close/morning | Devigged fair. Research reads this; never re-devig. |
| Kalshi K ladders | 2026-only exchange closes | Sharp *anchor*, not a fill book. |
| Raw JSON cache | 4,509 close + 4,680 morning event files | Source of truth. Re-normalizable. **Envelope timestamps recovered this turn.** |

Paid snapshots pulled: **close** (commence−5 min request) and **morning**
(commence−5h). There is **no paid `open` folder**. True overnight opens
are the friend CSV, frozen at 2026-07-10.

Books in the paid lake: DraftKings, FanDuel, Fanatics, BetMGM, Bovada,
BetOnline, BetRivers, William Hill US, MyBookie. Pinnacle is absent for
MLB props on `us` (already verified).

## 2. Integrity finding (this turn, $0)

Every raw historical JSON already wraps the event in vendor
`timestamp / previous_timestamp / next_timestamp`. The normalizer
ignored the wrapper and reconstructed `snapshot_ts` as commence−5 min/−5h.

Recovered envelope (`snapshot_envelope.parquet`, 9,189 rows, 100% coverage):

| Snapshot | n | vendor vs commence (p50) | reconstructed vs vendor |
| --- | ---: | --- | --- |
| morning | 4,680 | 300.4 min (clean 5h) | p50 +23s; 18 files >10 min off |
| close | 4,509 | 5.4 min | p50 +23s; **173 files >10 min off; 22 >1h** |

**Close leakage:** 12 events have vendor timestamp *after* commence.
Those must not be called closes. 119 closes sit >30 min before commence
(rain delay / commence ≠ first pitch). Replay must use **vendor
timestamp ≤ first pitch**, not reconstructed clock.

`previous_timestamp` / `next_timestamp` are present on every file. That
is the paging key for a 5-minute tick path — not a reason to pull one.

## 3. What Odds API can still give us

Credit model (paid historical event-odds): **10 × regions × markets ×
events × snapshots**. Remaining ~3.72M. Empty responses do not spend.

| Capability | Cost (approx) | Use | Verdict |
| --- | --- | --- | --- |
| Recover envelopes from raw JSON | **$0** | Point-in-time integrity | **DONE 2026-09-11** |
| Attach juiced DK/FD/median prices to 2025+2026 universe | **$0** | Harness currently fair-priced; juiced spike was 2026-morning only | **Next $0 build** |
| Paid K `open` snapshot (−30h) | ~47k credits (K-only, ~4.7k events) | Fills post-7/10 open gap on the same vendor as morning/close | Cheap, optional, after juiced replay exists |
| Featured `totals` / `h2h` / `spreads` via `/historical/.../odds` (whole slate per timestamp) | ~10 credits × days × snaps, not per event. ~5–15k for close+morning totals | Game-total / ML as **correlation / pace environment**, not a K signal | Cheap, useful for slate-shock caps |
| `totals_1st_5_innings` / `h2h_1st_5_innings` | 10 × events × snaps (per-event additional market) | Starter-relevant environment | Park until juiced K replay is honest |
| 5-minute prop ticks (page `previous`/`next`) | 12h × 12 snaps/h × 10 × 4.7k ≈ **6.7M** — over remaining quota | Intraday steam path | **Do not pull globally.** Optional 50–100 game sample later |
| `bookmakers=draftkings,fanduel` | Same 10-credit bucket for ≤10 books | Cheaper future pulls | Use on any new pull |
| `includeBetLimits` | Free field | Mostly exchanges | Skip for US books |
| `eu` / Pinnacle | Doubles region cost | MLB props still absent | Skip |
| Odds API scores | 1–2 credits | We settle K from Statcast/MLB API | Skip |
| Batter suite re-pull | Already on disk | No batter model | Park |
| `us2` (ESPN/Fliff/HardRock) | Full region doubling | Marginal books | Skip |

Friend opens already *are* Odds API historical at −12h (25,365) and −6h
(782). A paid −30h pull is a third clock, not the first open.

## 4. What a frozen-model replay should consume

Decision clock, in order, using only timestamps ≤ decision time:

1. Friend −12h open when present (through 2026-07-10).
2. Else paid morning (T−5h).
3. Never close as an input. Close is the **evaluation** benchmark.
4. Juiced American price at that clock: DK else FD else book-median
   (`juiced_price_spike.py` pattern, both years, not 2026-only).
5. Frozen `p_ours_cal` from `universe_panel_live` (no bundle reload).
6. Store **rejected** candidates as well as taken bets.
7. Grade vs paid close **and** vs actual K. Report CLV, Brier, juiced
   ROI, fill-scenario ROI separately.

Three fill scenarios, already specified, still unbuilt:

- Optimistic: best qualifying book.
- Realistic: DK-first then FD (our live path).
- Conservative: worse of expected fill and one tick of slippage.

If a policy is green only under optimistic, it is not ready.

## 5. What we must not do with this lake

- Do not retune live floors / veto / Kelly from a same-data sweep.
- Do not treat reconstructed `snapshot_ts` as first-pitch close.
- Do not 5-minute-tick the full 2025–26 prop book (quota + overfitting).
- Do not pull `us2` or Pinnacle-envy regions.
- Do not call consensus-beating “true probability.” Kalshi is the sharp
  *label*, DK/FD juiced is the money path.
- Do not pick the floor that maxed 2025 ROI and then “confirm” it on the
  same 2026 panel the harness already peeked (#93). Nested juiced v2
  waits for a locked 2026 judge after 2026-09-27.

## 6. Literature that maps onto this stack

- CLV is a **skill diagnostic**, not profit. Unabated: vig-free close,
  and CLV is weaker in illiquid props than in NFL sides. Our paid CLV is
  +0.26 pp (n≈1,100 undeduped) — right at the “maybe skill” line, which
  is why fills still block money claims.
- Calibration-selected models beat accuracy-selected models on betting
  ROI (Wagerproof / *Machine Learning with Applications* 2024 NBA study).
  That is the WS1c philosophy. It does **not** license Kelly on
  uncalibrated tails (morning ECE 0.10).
- White Reality Check / PBO / DSR belong on **policy configs**, not on
  the frozen bundle. Our 56-config harness is exactly the snooping
  surface those tests were built for.
- Fractional Kelly under parameter uncertainty (Baker & McHale-class /
  INFORMS *Decision Analysis*): shrink the fraction when *p* is
  estimated. 1/16-Kelly is the conservative industry default. Flat 1u
  remains the research benchmark so sizing cannot manufacture edge.

## 7. Recommended build order (research only)

1. **DONE:** envelope recovery.
2. **Next ($0):** juiced-price attach for **both years** at open and
   morning onto `universe_panel_live` (DK→FD→median), plus rejected-
   candidate logging in a policy-neutral 1u ledger.
3. Flag the 12 post-commence “closes” as `close_invalid`.
4. Optional cheap pull: featured `totals` at morning+close (~thousands
   of credits) as a slate-correlation feature.
5. Optional cheap pull: K-only `open` (−30h) to cover 2026-07-11→season
   end (~47k credits).
6. Nested juiced policy v2 **after 2026-09-27**, 2025-select / 2026-judge
   once, White/PBO over the config family. No live floor change until
   that judge is locked.

The frozen model already produces the probabilities. The Odds API lake
already produces the prices. The research job is to stop confusing
fair-price ROI, reconstructed clocks, and thin-cell floors with
executable alpha.
