# Frozen-model Odds API replay — standing architecture

> **Not a work queue.** Approvals and next builds live only in
> [`docs/EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md). This file is the
> durable spec for *how* a 2025-present open→close backtest must be built
> now that the Odds API lake is on disk. If this file’s “next” disagrees
> with the Session Snapshot, the Snapshot wins — then fix this file.
>
> Point-in-time inventory (counts, quota, envelope diagnostics):
> [`reports/oddsapi_replay_inventory_2026-09-11.md`](reports/oddsapi_replay_inventory_2026-09-11.md).
> Pull protocol: [`clv_backfill_plan.md`](clv_backfill_plan.md) (buy is DONE;
> this file inherits the timestamp / book / credit doctrine).
> Process: [`experiment_sop.md`](experiment_sop.md).
> Numbers: [`golden_metrics.md`](golden_metrics.md) — cite, do not recompute.

**Locked decision (2026-09-11):** keep the production model frozen. Research
lives in the **policy, calibration-application, market-construction, and
execution** layers. Retrain path is closed (`retrain_spec.md` §7). Nested
juiced policy re-judge is post-2026-09-27, not a same-week floor retune.

---

## 0. One-sentence doctrine

The current live board is a **risk-control system supported by incomplete
evidence**, not a proven optimal betting policy. Floors, gates, and sizing
are separately testable policies. They must be evaluated on frozen-model
probabilities against **timestamped, book-specific, juiced** Odds API
prices, with rejected candidates retained and fills still unlabeled.

That sentence is the product thesis. Everything below is how not to
violate it.

---

## 1. Freeze / work / product — the operating partition

This is the most important table in the file. Agents and future-you
should not “improve the model” when the binding constraint is replay
honesty and fills.

### Freeze (do not touch without explicit sign-off)

| Surface | Why frozen | Reopen only if |
| --- | --- | --- |
| k-rate LightGBM ensemble (sparse72 / mono / final58) | Train 2023–24; 19 feature kills; walk-forward dead | New data source in hand **or** offseason full-season review |
| TBF ridge (2026-07-28 stem) | Three two-stage mixtures killed; marathons irreducible pregame | Same |
| Count family = Poisson | 7/8-line race; BB/NB ≈ Poisson | Challenger clears SOP on universe Brier |
| WS1c per-line Platt maps | Live 2026-09-10; ship-lift +0.0016 measured | Chrono challenger + sign-off |
| 4.5-over hard veto | Risk control, weekly pack green 4×, CIs still wide | Nested **juiced** 2025-select / 2026-judge after 9/27 |
| Line floors in `line_floor_policy.json` | 9/01 thin-n diagnostics; **not** ROI maxima | Same nested juiced judge |
| 2.5/3.5-over probation (0.20 / 0.18) | Aging n≈35 origin; mixed current reads | Same |
| `DEFAULT_KELLY_FRACTION = 0.0625` (1/16) | Conservative under tail miscalibration | Fill-backed bakeoff vs flat 1u |
| Live SharpAPI path | Daily board; not the historical archive | Hosting cutover |
| Regular-season-only / postseason HOLD | 2026-09-27 cut; no playoff panel | Owner changes season key |
| Odds never enter the trainer | `market_clv_gates.md` separation | Never |

### Work (research / ops — still not live policy)

| Work | Status 2026-09-11 | Why it matters |
| --- | --- | --- |
| Vendor snapshot envelopes | **DONE** (`recover_snapshot_envelope.py`, 9,189 rows, 100% coverage) | Reconstructed clocks lie on delayed games; 12 “closes” are after commence |
| Juiced-price attach, **both years**, open + morning | **DONE #123** (`juiced_replay_ledger.py`) | Live floors speak juiced; GO said DK→FD→median, script uses next-book fillable fallback |
| Rejected-candidate logging | **DONE #123** (reasons: below_floor / veto / no_two_way / bad_price) | Filter alpha vs hidden tickets is now countable |
| Policy-neutral flat-1u ledger | **DONE #123** (+ Kelly / band / robust shadow arms) | Isolates signal from Kelly magnification; flat beat 1/16-Kelly on ROI |
| Envelope-aware close validity flag | **DONE #123** (CLV omitted when vendor ts after commence; 12 events) | 12 post-commence closes must not grade CLV |
| Nested juiced v2 (2025 select / 2026 judge once) | Gated post-9/27 | Prior harness peeked 2026 twice (#93). 2026 juiced ROI +12.6% is confirmatory folklore |
| White Reality Check / PBO / DSR on **policy configs** | Unbuilt | 56-config search is a snooping surface |
| Real fills (≥50 Novig) | Owner-blocked | Paper ≠ money. Canonical next-book juiced 1u is the paper bar before small stakes |
| Dawn SharpAPI probe / NightlyDrift register | Owner ops | Timing doctrine is untested on live carriage |
| Offset cap 0.02 / stacker stage 2 / morning edge cap | Research-done, need go | Production-safe placement is **stacker stage 2 shadow only**; do not change BET set from this ledger |
| DK+FD vs next-book fill set | **LOCKED next-book** (owner 2026-09-11) | Canonical = coverage. DK+FD-only stays a sensitivity in the report |
| Featured game totals (morning+evening calendar clocks) | **DONE #124** (`featured_totals.parquet`, 220,482 rows / 4,749 events / 363 days) | Slate correlation / pace / common-shock — not a K feature. ~7.3k credits spent |

### Productize later (not this season)

A product is not “the Streamlit dashboard.” A product is a system that
takes a bankroll, emits executable tickets, records fills, and survives
an audit. That requires the freeze layer to stay frozen, the work layer
to be honest, and then:

1. Proven **flat-1u** positive expected value after vig and a realistic
   fill scenario (not optimistic best-book).
2. Actual fills with rejected-bet logging (limits, re-quotes, vanish).
3. Correlation-aware exposure (per-game, per-team, per-side, common-shock).
4. Kill-switch + postseason/regime hold already exist; they must stay
   mechanical, not discretionary.
5. SLA: morning board by a published clock, failure banners (already
   built), quote freshness, settle hard-guard (already built).
6. Legal/compliance: this repo is a personal research desk. Turning it
   into a product (tips, copy-trading, a fund, a SaaS) is a different
   company — geo, age, ToS, advertising rules, not a code task.

Until (1)–(3) are true, call it **paper operations with institutional
hygiene**, not a betting product.

---

## 2. What is already done well

This project’s edge over a typical sports-model repo is process, not a
magic MAE.

**Separation of layers.** Baseball probabilities never train on odds
(`market_clv_gates.md`). The strikeout stack is `k_rate × projected_TBF →
count layer → per-line Platt`. Market math (devig, edge, Kelly, CLV) is
a product layer. That is the correct architecture for any shop that has
to explain a loss.

**Kill culture.** Nineteen workstreams died in writing with kill
criteria declared *before* the run. Dead code stays; live policy does
not absorb a survivor from the wrong panel. That is how you avoid the
graveyard of “we tried that, it looked good on Tuesday.”

**Frozen inference at universe scale.** 8,775 starts scored without
refitting; 71,080 live-config line-points. Books beat us on close
probabilities (skill −0.0043, n=19,533). We beat the opener (+0.044).
Those two facts together are the whole strategy: **timing + selection**,
not a better GBM.

**Honest demotion.** Modeling half of the paper is claimable. Betting
half is demoted. Golden metrics forbid recomputing folklore. Parallel
ledgers exist for A/B. Atomic parquet writes exist after a corruption
scare. Settle will not grade pregame K=0. Postseason is HOLD. That is
desk-quality ops.

**Paid lake with raw JSON forever.** 4,509 close + 4,680 morning event
files, 1.64M pitcher rows, 10.9M batter rows parked, 9 US books, credit
floor at 10%, closes-first pull order. Re-normalization never re-spends.
Friend −12h opens share the same `event_id` space (2,928 overlap). This
is enough data to do the replay correctly. It is not a reason to keep
buying.

**What is not done well (ranked).** Fills (blocking all money claims) →
reconstructed close clocks (12 leakage events; 173 >10 min off) →
fair-vs-juiced confusion in the policy harness → morning ECE 0.10 →
policy-search overfitting (floors × gates × caps × brake) → thin
line×side cells → correlated slate exposure hidden by a 12u/20u cap →
CLV treated as profit.

---

## 3. Floors, probation, gates, sizing — how to read the live policy

Live values (`line_floor_policy.json` + `kpi_policy.json`):

| Line | Min juiced edge |
| ---: | ---: |
| 2.5 | 0.20 |
| 3.5 | 0.18 |
| 4.5 | 0.14 (and **hard veto** on overs) |
| 5.5 | 0.14 |
| 6.5 | 0.12 |
| 7.5 | 0.12 |
| 8.5 | 0.14 |
| 9.5 | 0.16 |

Base 0.12, elevated to 0.14 when model-health warnings ≥ 2. Stakes:
edge-based units at $50, slate caps 12u soft / 20u hard; drawdown brake
shadows CAUTION ×0.5 (not live).

**These floors are minimum evidence thresholds, not ROI maxima.** They
were set 2026-09-01 from open-era segment ROI plus sweep governance, on
thin samples, and have not been re-derived. A thin 6.5/7.5-over cell at
fair open-mixed prices does not authorize unleashing overs; juiced
paper plus the veto’s own evidence still dominate until the nested
re-gate.

Probation (2.5/3.5 overs) is a **risk control with a higher floor**,
same family as the veto — not the max-ROI point of those lines.

Support gates:

| Gate | Status |
| --- | --- |
| TBF ≥ 15 | Evidence-backed (WS3 tails). Prefer continuous shrinkage over a hard cut when replay exists. |
| Long-rest / matchup-tier blocks | Legacy August fits. Re-gate October. Do not trust blindly. |
| Quality-gate dynamic floor | Live; health-state only. |
| Deploy matrix | Live; 24d stale at last audit; universe-scale re-gate pending. |

**Do not claim 1/16-Kelly is “optimal.”** It is half of eighth-Kelly, the
literature’s conservative default when *p* is estimated. Full Kelly on
decimal odds *d*, model probability *p*, *b = d−1*:

\[
f^* = \frac{bp - (1-p)}{b}, \qquad f_{\text{live}} = \tfrac{1}{16} f^*.
\]

This is only meaningful if *p* is calibrated, the odds are executable,
edge is vs the correct no-vig (or explicitly juiced) benchmark, and
correlation is capped. A useful robust form for a later shadow arm:

\[
f_{\text{robust}} = \lambda_{\text{model}}\,\lambda_{\text{health}}\,\lambda_{\text{fill}}\,\lambda_{\text{corr}}\,f^*
\]

with each λ ∈ [0,1]. Flat 1u is the **research benchmark**. If the
signal is real it must show up under flat staking before Kelly
magnifies it. Switching live to 1u is a policy change, not a bugfix.

**Filter order.** Not “over/under first.” Sequence:

1. Freeze the model prediction.
2. Normalize the market; strip vig for *measurement*; keep juiced for *PnL*.
3. Price-specific edge at the decision clock.
4. Data-quality and availability (books present, TBF support, not postseason).
5. Line-by-side policy surface (hierarchical shrinkage; min-n).
6. Exposure and stake constraints (game / team / side / slate / shock).
7. Record accepted **and** rejected.

Cells genuinely differ by line×side. Eight lines × two sides × price
bands × books × health states is a multiple-testing machine. Partial
pooling (`θ_{l,s} ~ N(μ_l, σ_l²)`) is the correct estimator, not
independent cell averages.

---

## 4. Data lake — what a replay is allowed to read

### Canonical clocks (never mix their jobs)

| Clock | Source | Use |
| --- | --- | --- |
| Open | Friend CSV `pitcher_strikeouts_early_open_2025_2026.csv` (−12h 97% / −6h 3%), 2025-03-27→2026-07-10 | Decision time when present |
| Morning | Paid Odds API, requested commence−5h | Decision time otherwise; T−5h is the live-deployable proxy |
| Close | Paid Odds API, requested commence−5min, **vendor timestamp ≤ first pitch** | Evaluation only |
| Settlement | Statcast / MLB API K | Outcome. Odds API scores endpoint is unused. |

Paid lake: `data/Odds-Historical/theoddsapi/` (gitignored). Raw JSON is
the source of truth. Normalized: `book_lines_pitcher.parquet` /
`book_lines_batter.parquet`. Consensus: `consensus_cache.parquet`
(devig-median; research reads this, never re-devigs). Envelopes:
`snapshot_envelope.parquet` (vendor `timestamp/previous/next`).

Live polling remains SharpAPI (`SHARPAPI_KEY`). Historical research
remains the-odds-api.com (`THEODDSAPI_KEY`). Do not confuse them.

### Timestamp doctrine (updated 2026-09-11)

The historical event-odds response is an **envelope**:

```text
{ timestamp, previous_timestamp, next_timestamp, data: { id, commence_time, bookmakers: [...] } }
```

`pull_oddsapi_historical.normalize` currently reconstructs `snapshot_ts`
as commence−5min/−5h/−30h from the inner event and drops the wrapper.
Envelope recovery showed 100% of 9,189 files already had vendor
timestamps.

- Morning reconstruction is usually fine (p50 +23s vs vendor).
- Close reconstruction is **not**: 173 files >10 min off, 22 >1h, **12
  vendor timestamps after commence**.
- Replay must join `snapshot_envelope.vendor_timestamp` and refuse any
  close with `vendor_timestamp > commence_time` (and, when first-pitch
  from Statcast exists, `> first_pitch`).
- The API returns the closest snapshot **at or before** the requested
  `date`. Never forward-fill from `next_timestamp`. Paging
  `previous_timestamp` is how a 5-minute tick path would work — it is
  not a reason to pull one.

### What we will not pull (quota remaining ~3.72M / 5M)

| Idea | Why not |
| --- | --- |
| Global 5-minute K ticks | ~6.7M credits; overfitting theater |
| `us2` / Pinnacle `eu` | Region doubling; Pinnacle absent for MLB props |
| Odds API scores | We already settle K |
| Batter re-pull | 10.9M rows already parked; no batter model |
| `includeBetLimits` | Exchange field; US books do not carry it usefully |

Cheap optional later (owner): K-only −30h `open` to cover 2026-07-11→season
end (~47k). Featured totals are owner-GO 2026-09-11
(`pull_featured_totals.py`). Neither unblocks a live floor retune.

---

## 5. Replay engine specification

Event-centric, not ticket-centric. The current `decision_grade_harness.py`
is a policy search over fair probs. It is the ancestor, not the engine.

### 5.1 Immutable event table (target schema)

One row per (event_id, book, market, outcome, line, snapshot) plus:

- sport / league / home / away / commence_time
- vendor_timestamp, previous_timestamp, next_timestamp
- bookmaker last_update
- American price, implied, vig-stripped fair (when two-way)
- source endpoint, requested `date`, whether `vendor_timestamp ≤ decision_ts`
- later: result, settlement_ts, ingest_ts

Rejected candidates are first-class rows with `accepted=false` and a
reason code (`floor`, `veto`, `tbf`, `rest`, `postseason`, `no_book`,
`close_invalid`, …).

### 5.2 Decision replay

For each historical decision time:

1. Reconstruct only what the system would have known (`p_ours_cal` from
   the frozen live panel; no bundle reload).
2. Use only snapshots with `vendor_timestamp ≤ decision_time`.
3. Select the eligible book under the **named fill scenario**.
4. Apply candidate policy.
5. Simulate fill (1.0 until we have empirical fill rates; then a model).
6. Store accept and reject.
7. Join settlement later. Close is a grade, not an input.

### 5.3 Fill scenarios (all three, always)

| Name | Meaning |
| --- | --- |
| Optimistic | Best qualifying book |
| Realistic | DK else FD else median (live path) |
| Conservative | Worse of expected fill and one tick of slippage |

If a strategy is profitable only under Optimistic, it is not ready.

### 5.4 Shadow ledgers (pre-registered, parallel)

| Ledger | Purpose |
| --- | --- |
| Flat 1u | Signal quality without sizing |
| Edge-banded flat | Whether stronger edges deserve size |
| 1/16-Kelly | Current production baseline |
| Robust Kelly | Shrunk *p*, health, fill, correlation λ’s |

Primary **research** metric order: CLV → calibration → EV after vig and
execution assumptions → realized ROI → drawdown / tail → volume / fill
rate. Realized ROI is last because it is noisy. CLV is not profit.

### 5.5 Nested evaluation (policy, not model)

Inner loop: candidate floor vectors / gates / sizing, information
available at bet time only, frozen probs.

Outer loop: chronological blocks.

- Research: earlier 2025 months.
- Validation: later 2025.
- Locked test: 2026 regular season, **once**, after 2026-09-27.
- Forward: live paper / small stakes.

Champion rule is **not** max ROI. Prefer a constraint set: LCB_95(ROI) > 0
on block-bootstrap (slate-clustered), CLV ≥ 0 after vig, stable
calibration, no single line/side dominating, robustness across books and
health states. Report the number of configs tested. White’s Reality
Check / PBO / Deflated Sharpe belong here.

The 2026-09-10 harness (56 configs, fair prices, reconstructed clocks,
peeked 2026 twice) is **confirmatory folklore**, not this judge.

---

## 6. Methods worth adding (research menu, not a queue)

These are valid next science *after* the juiced 1u ledger exists. Do
not start them to look busy.

- **Hierarchical shrinkage** of line×side ROI instead of cell averages.
- **Isotonic / beta calibration** only inside time-respecting folds;
  ECE with confidence intervals (morning ECE 0.10 may or may not differ
  from the long-run baseline).
- **Conformal prediction** around expected_K / edge; suppress when the
  lower bound on edge is ≤ 0. Not a profitability proof — a model-risk
  layer.
- **Distributionally robust sizing:** size against *p* ∈ [p−δ, p+δ] or a
  lower posterior quantile, not the point estimate.
- **Regime monitors** with a *pre-declared* response (calibration, CLV,
  fill rate, health warnings, selected-bet distribution). Sequential
  peeking without a rule is another overfit.
- **Featured game totals** as a common-shock factor for slate caps
  (cheap Odds API featured endpoint).
- **Kalshi vs DK/FD** as a three-way skill triangle (exchange / soft
  book / model) — already scaffolded; keep labels honest.

GARCH, Pinnacle envy, global floor sweeps, umpires (ABS), minors
translation, and MLflow-as-ops stay on the program disregard list.

---

## 7. Product-grade bulletproofing

What “bulletproof” means here is **an auditor can reconstruct every
ticket from raw JSON + frozen hashes + policy version**. Not “the ROI
never goes red.”

### Integrity

- Raw Odds API JSON retained forever; parquet is a projection.
- Vendor envelope timestamps on every research join.
- Frozen bundle stems + WS1c pointer + Poisson default pinned by
  regression tests (`#113.4`).
- Atomic ledger writes; settle hard-guard; vanish tracking.
- Deduped paper track (`dedupe_ledger_props`) for any money sentence.
- Close-invalid flag for post-commence snapshots.

### Research

- SOP: bins first, same-subset Brier, single-feature, shadow → gate →
  sign-off, nested 2025/2026 only once per policy family.
- Golden metrics: cite, do not recompute.
- Rejected-candidate store so filters are estimable.
- Block bootstrap, not iid Bernoulli, for slate PnL.

### Operations

- Morning failure banners already exist; NightlyDrift still needs owner
  registration.
- Shared SharpAPI fetch (#113.3) so board and poll do not race.
- Postseason mechanical HOLD.
- Keep-awake on long tasks (Modern Standby incident 9/6–9/8).

### Product (future)

- Fill ledger with decision-time price, stake, book, accept/reject,
  latency, limit.
- Per-game / per-team / per-side / correlation caps in front of slate
  caps.
- Published SLA and a kill-switch that is a config key, not a chat.
- Model card + policy card versioned together (we have pieces; they are
  not a single customer-facing artifact).
- If other people’s money: entity, geo-restriction, no-advice
  disclaimer, and a compliance review. Code cannot skip that.

---

## 8. Capability roadmap (spec order, not a sprint)

Treat this as the construction sequence for the replay. **Do not execute
it as a queue** — Snapshot FORWARD names the next build.

1. Immutable Odds API snapshot lake with raw JSON — **DONE**.
2. Event canonicalization + book/market normalization — **DONE**
   (split pitcher/batter; envelope recovery added 2026-09-11).
3. Point-in-time replay engine — **NOT BUILT**.
4. Opening / decision / closing reconstruction using **vendor**
   timestamps — envelopes recovered; joins not yet switched.
5. Execution scenarios + fill simulation — **NOT BUILT**.
6. Flat-1u, 1/16-Kelly, robust-Kelly, edge-band ledgers — **NOT BUILT**.
7. Line×side hierarchical shrinkage — **NOT BUILT**.
8. Block bootstrap / clustered CIs — weekly pack has percentile
   bootstrap; slate-clustered not standard yet.
9. White / PBO / DSR / PSR on policy configs — **NOT BUILT**.
10. Rejected-candidate logging — **NOT BUILT**.
11. Game/team/side/correlation caps — slate caps only.
12. Calibration-drift + CLV monitoring — NightlyDrift + weekly pack
    exist; envelope-aware CLV does not.
13. Re-gate legacy support rules — October.
14. Re-evaluate floor vectors only on the locked split — October.
15. Untouched forward period — live paper after the judge.

The proper near-term decision is **not** “raise or lower floors” and
**not** “Kelly vs one unit.” It is whether the frozen model produces
positive, calibrated, **executable** edge under a policy-neutral 1u
ledger at juiced DK/FD prices. Once that is demonstrated, sizing and
floors can be optimized conservatively without confusing policy
overfitting for alpha.

---

## 9. File map

| Path | Role |
| --- | --- |
| `production/ops/market_research/pull_oddsapi_historical.py` | Paid pull + normalize (reconstructed `snapshot_ts` still) |
| `production/ops/market_research/pull_regular_season_closeout.py` | Day-by-day close+morning through 2026-09-27 |
| `production/ops/market_research/recover_snapshot_envelope.py` | $0 vendor envelope recovery |
| `production/ops/market_research/join_universe.py` | Frozen scores ⋈ books |
| `production/ops/market_research/decision_grade_harness.py` | Fair-price ancestor harness (peeked; not the judge) |
| `production/ops/market_research/juiced_price_spike.py` | 2026-morning juiced translation only |
| `production/ops/market_research/line_floor_policy.json` | Live line floors |
| `production/ops/kpi_policy.json` | Veto, probation, TBF, rest, postseason |
| `src/Python/market.py` | Devig, edge, 1/16-Kelly |
| `src/Python/odds_board.py` | Live accept/deny |
| `artifacts/odds_log/universe_panel_live.parquet` | Frozen live-config probs |
| `data/Odds-Historical/theoddsapi/` | Paid lake (ignored) |
| `data/Odds-Open-Close-2025-2026/` | Friend opens (ignored) |

---

## 10. How a future session should use this file

1. Open the backlog Snapshot. If FORWARD does not name replay work, do
   not start it from this document.
2. If building replay: freeze the model, use vendor timestamps, speak
   juiced prices, keep rejects, run Optimistic/Realistic/Conservative,
   lead with flat 1u.
3. If tempted to retune floors, Kelly, veto, or WS1c: stop. That is a
   sign-off, and only after the locked juiced judge.
4. Cite golden metrics. Do not recompute universe Brier from memory.
