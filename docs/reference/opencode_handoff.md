# OpenCode / Cursor handoff — 2026-09-11 (replay era)

> **Paste this file into a new OpenCode or Cursor session.** It is a
> coworker briefing, not a second work queue. Approvals and next actions
> live only in [`docs/EXECUTION_BACKLOG.md`](../EXECUTION_BACKLOG.md).
> If this file and the Snapshot disagree, the **Snapshot wins** — then
> fix this file.
>
> Prior version (2026-09-10) covered #107–#113 notebooks / nested-hole /
> backend pack. That material is still true. This rewrite adds the
> frozen-model Odds API replay (#121–#124) and the product partition.
> Do not re-run #66–#110.

---

## START HERE (do this, not the 400-line backlog dump)

**You are joining a live desk whose model is frozen and whose remaining
work is policy, market construction, execution, and fills.** Retrain
path is closed (`retrain_spec.md` §7). Dashboard v1 is PARKED. Do not
edit Streamlit. Do not retune floors / veto / Kelly / WS1c / Poisson /
KING.

**Read, in order:**

1. `docs/EXECUTION_BACKLOG.md` — Snapshot PAST / PRESENT / FORWARD /
   DEFERRED + Waiting on user. FORWARD numbered items 10–17 and every
   `#NN` diary bullet below the **pickup box** are historical. They are
   not a queue.
2. This file.
3. `docs/reference/oddsapi_replay_architecture.md` — freeze / work /
   product. Not a queue.
4. `docs/reference/golden_metrics.md` — cite, do not recompute.
5. `docs/reference/experiment_sop.md` §8 — same-subset skill, nested-hole
   rule, vendor envelopes, juiced book-pick rule.
6. Dated juiced evidence:
   `docs/reference/reports/juiced_replay_ledger_2026-09-11.md`

**Cite numbers from golden metrics + the JSON it names.** Canonical
paper money = `dedupe_ledger_props`. Raw ledger `clv_pp` n=975 is
undeduped watcher fills. Universe Brier is `rescore_cal_report.json`
pooled. Juiced 1u is `juiced_replay_report.json`. Do not recompute any
of those.

**Two odds vendors. Do not mix.** Live board = SharpAPI (`SHARPAPI_KEY`).
Historical lake = The Odds API (`THEODDSAPI_KEY`). Friend −12h opens are
Odds API historical already in a CSV. Remaining quota ~**3.71M / 5M**
after the featured-totals pull.

**Owner is directing jobs again (2026-09-11).** Pack #113 steps 0–4 are built. Juiced
ledger #123 is measured. Totals #124 are pulled **and joined**
(`slate_shock_join.py` → 1,633 correlated pairs quantified). Live changes
since polish-then-stop: morning `edge_cap = 0.20` + `robust_refusal` +
`offset_cap = 0.02` — all named, tested (336 green), pinned same commit.
Ops habits (settle, weekly pack, closeout) are always allowed. Further live
BET-set changes still need a named order. Snapshot wins over this file.

---

## 0. What this system actually is

A personal MLB pitcher-strikeout prop desk. The baseball model never
sees odds (`market_clv_gates.md`). The stack is:

```
Statcast / L3 features
  → k-rate LightGBM ensemble (sparse72 / monotone / final58; train 2023–24)
  → TBF ridge (projected plate appearances)
  → Poisson count layer  →  P(K > line) at 2.5..9.5
  → WS1c per-line Platt maps (live 2026-09-10)
  → policy filter (floors, 4.5-over veto, 2.5/3.5 probation, TBF≥15,
     deploy matrix, postseason HOLD 2026-09-27)
  → size (1/16-Kelly, unit $50)
  → SharpAPI live quotes → BET/HOLD on odds_board → ntfy
```

Market math (`src/Python/market.py`: multiplicative de-vig, edge, Kelly,
CLV) is a **product layer**. That split is load-bearing. If you let
closes into the trainer you cannot explain a loss.

Live production path:

`odds_board.py` → `poll_odds.py` → `ledger.parquet` →
`grade_odds_ledger.py` → frozen-edge-watch → quality gate → weekly pack.

Research path (frozen inference, never a re-spin):

`score_historical_range.py` → `join_universe.py` →
`universe_panel_live.parquet` (71,080, Poisson+WS1c) → cells / gates /
`juiced_replay_ledger.py`.

The owner is trying to turn this from “a model with a board” into
**paper operations with institutional hygiene**, and eventually into a
system that takes a bankroll, emits fillable tickets, records what did
not fill, and survives an audit. A Streamlit dashboard is not that
product. Neither is another LightGBM.

---

## 1. Where we were (through 2026-09-10)

### Modeling era — exhausted, on purpose

The beat-the-books program (`beat_the_books_program.md`) diagnosed a
two-layer disease on the 6-week paper track and then confirmed it at
universe scale:

1. **Probability:** books are nearly perfectly calibrated (consensus ECE
   ~0.015). We are not (BET-selected ECE was 0.159; universe ECE 0.021
   after WS1c — the disaster was selection, not the calibrator failing
   on unselected data).
2. **Selection amplifier:** the edge floor preferentially takes tickets
   where we over-predict xK by +0.7–0.9 (global bias ~+0.05). Over-bleed
   is not “we hate aces.” Mid-bin xK 4–6 bleeds spread-wide. 4.5-overs
   are the toxic cell.
3. **Timing:** same-game skill is **+0.044 vs friend opens** and **−0.004
   to −0.006 vs morning/close**. Edge decays −12h → −5h. Morning ≈ close.
   Never chase. Day games on the live ledger are bet later (median −2.6h
   vs night −6.4h) and lose more — carriage, not just model.

Nineteen workstreams were killed in writing with criteria declared
*before* the run (blend w=0, recency, TBF mixtures ×3, command, kAdj both
vehicles, family-vulnerability, age walk-forward, NB, slots, …). The
two that shipped live are **WS1c per-line Platt** and **Poisson**.
Retrain path closed at #66. Reopen only on new data or offseason
full-season review.

KSplit is an external benchmark (MAE 1.749 vs our 1.78; bias 0.03 vs
0.11), not a gospel and not a license to copy their stack. Even they
are roughly breakeven. ROI in this market comes from **timing +
selection + fills**, never from raw Brier alone.

### Process hole — the most important past finding

The owner asked for nested design: lock filters on **2025** open+close,
simulate **2026** once, then wire production.

What shipped live did **not** follow that:

| Live piece | How it was picked | Nested? |
|---|---|---|
| 4.5-over veto, 2.5/3.5 probation, floors | 2026 post-freeze paper n≈74, then 2026 weekly pack | **No. In-sample 2026.** |
| WS1c Platt | 70/30 cut 2026-05-23 on 2025–2026 universe | **No.** Ate 2025. |
| Distill stacker | Cut 2026-05-21 | **No.** |
| Price offsets | Fit 2026-08-21 on pre-freeze opens | **No.** |
| `decision_grade_harness.py` | 2025 select / 2026 judge | **Yes, then contaminated.** Not promoted. |

Harness contamination, still true, still not “fixed” by more 2026 paper:

1. `snap=best` mixes friend **−12h opens** (~30pp overnight-soft) with
   paid morning. 2025 fair ROI of +50–100% with hugely negative CLV is
   steam correcting stale opens, not proof we beat close.
2. Odds API lake is morning + close, not vendor open. Paid `open` folder
   does not exist. Friend CSV ends 2026-07-10.
3. Harness spoke **fair** prices. Live floors speak **juiced**
   (translation ≈ −3.3pp).
4. #93 peeked 2026 twice (bug → re-pick → read 2026 again). Remaining
   2026 is confirmatory folklore.
5. Live stack (offsets, deploy matrix, Kelly) was missing from the
   harness. It selected a different object than the board bets.

**Do not retune live veto/floors from more 2026 paper, including the
juiced 2026 slice.** That doubles the hole. Clean juiced nested re-judge
(2025-select / 2026-judge **once**, juiced, full live stack as one
pre-registered family) is **post-2026-09-27**.

### Backend pack — built, not a live-policy change

Pack #113 steps 0–4 are green: paid clocks on the live ledger
(observability), settle hard-guard (pregame K=0 cannot settle), recs
offset-share / opener / reason columns (flag, no cap), shared SharpAPI
fetch for board+poll, regression pin on Poisson / WS1c / veto /
probation / postseason / vanish / atomic ledger. **BET set was not
touched.** Dashboard stays parked.

Ops hardening around this (keep-awake, failure-banner alerts, atomic
ledger writes, ntfy-only) is real. The 9/6–9/8 silent mornings and the
9/4 stale-slate zero-bet are closed incidents, not open bugs.

---

## 2. Where we are (2026-09-11, replay era)

The binding constraint stopped being “train a better k-rate model.”
It became: **evaluate the frozen model at the prices a human could
have bet, at the clock they could have bet them, keeping the tickets
we refused.**

### Integrity

Every raw historical JSON already wrapped `timestamp / previous /
next`. The normalizer dropped the wrapper and reconstructed
`snapshot_ts` as commence−5min / −5h. Recovered
`snapshot_envelope.parquet` (9,189 rows, 100%). Close p50 lag 5.4 min,
but **12 vendor timestamps after commence** (not closes) and 173
reconstructed clocks >10 min off. Replay uses vendor timestamps.
Never forward-fill `next_timestamp`. 5-minute prop ticks would cost
~6.7M credits — over remaining quota — and are refused.

### Juiced 1u ledger (#123) — the new money-shaped measurement

`production/ops/market_research/juiced_replay_ledger.py`

Contract:

- Frozen `p_ours_cal` from `universe_panel_live`.
- Two-way multiplicative de-vig at a **juiced book pair** (same
  `evaluate_side` as live).
- Decision: friend OPEN if both sides else paid MORNING. Close is
  evaluation only.
- Book: DK else FD else next US book with a two-way quote.
- Live policy as a **filter** (floors + 4.5-over veto + 2.5/3.5 bump
  0.18). Rejected rows kept (`below_floor` / `veto_4_5_over` /
  `no_two_way_price` / `bad_price`).
- Four shadow sizing arms. Fills unmodeled.
- 2026 labeled confirmatory.

Owner GO was DK→FD→median. Median is not a fillable ticket. Script
implemented next-book. Owner then **locked next-book as canonical**
(coverage over purity). DK+FD-only is a sensitivity, not the headline.

| Slice | n | ROI | WR | CLV pp |
|---|---:|---:|---:|---:|
| **All-books flat $50 (canonical)** | 2077 | **+7.3%** | 0.506 | +1.08 |
| DK+FD-only | 982 | +12.3% | 0.580 | +1.37 |
| 2025 (selection year) | 1308 | +4.2% | 0.487 | +0.95 |
| 2026 (confirmatory) | 769 | +12.6% | 0.540 | +1.30 |
| 1/16-Kelly | 2077 | +6.6% | 0.506 | +1.08 |

Sizing did **not** beat flat on ROI. Robust Kelly only looks better
because 266 tickets go Kelly-zero after shrinking p toward 0.5.

**Book mix is the finding, not a footnote.** BetRivers is 1,001 / 2,077
tickets (+2.3% ROI, WR 0.429, open-share 0.20). DK n=847 WR 0.580 ROI
+12.0%. FD n=135 WR 0.585 ROI +14.4%. BetRivers was already a QA flag
(alt-line bleed, 24k props vs ~8k/book). Next-book soaks it at morning
when DK/FD lack two-way. That is a **coverage vs purity** trade, not
evidence BetRivers is a good fill. Live SharpAPI path is usually DK+FD;
do not naively ship “the juiced +7.3%” as the production EV.

Probation (data, not a live change): skip-all 2.5/3.5-over is noise
(+7.41% vs +7.28%). 2.5-over n=18 thin-red. 3.5-under n=42 thin-red.
Freeze current probation. Owner asked to “retune from this juiced run”;
Cursor **refused**. 2026 +12.6% is the peek. 2025 +4.2% on the softer
mix they kept is the honest selection-year number. A live change
requires a **named** edit plus written peek-acceptance.

### Featured totals (#124) — slate environment, not a K feature

`pull_featured_totals.py` → `data/Odds-Historical/theoddsapi/featured_totals.parquet`

Whole-slate historical `/odds` (10 credits × regions × markets per
timestamp, **not** per-event). 726 snapshots, 7,260 credits, remaining
**3,714,815**. 220,482 rows / 4,749 events / 363 game-days. Two-way
balanced, median line 8.5, vendor envelopes kept (0 null timestamps).
Clocks are **calendar** 12:00 ET and 19:55 ET, not first-pitch. Not
joined to the K ledger yet. Purpose: common-shock / pace / slate caps.
Do not treat as a strikeout predictor.

### What is live vs not

**Live today:** 4.5-over hard veto, 2.5/3.5 probation floors 0.20/0.18,
line floors in `line_floor_policy.json`, TBF≥15, deploy-matrix filter,
quality-gate dynamic floor, WS1c, Poisson, 1/16-Kelly, postseason HOLD
2026-09-27, pack #113 observability.

**Shipped live 2026-09-11 (owner order):** offset cap 0.02 (silent clip,
visible via offset columns); morning edge cap 0.20 (`edge_cap` HOLD);
robust refusal (`robust_refusal` HOLD). Sizing of survivors unchanged.
**Still needs a one-liner go:** stacker stage 2 (**shadow `p_stacker`
only** — HOLD/BET untouched); drawdown brake ×0.5 as live staking
(owner parked 2026-09-11: stay confident, follow the edge).

**Owner-only:** register `MLBProps_NightlyDrift`; dawn SharpAPI probe
~05:00–06:00 ET; Novig fills ≥50 before any money-edge claim;
`git push origin HEAD`.

**Do not start without Snapshot FORWARD naming it:** October nested
juiced v2, 5-min ticks, −30h K open (~47k), Streamlit, MLflow, retrains,
global floor sweeps, panel-aware notebooks (they still read SharpAPI
`ledger.parquet`).

---

## 3. Vision — freeze / work / product

This is the operating partition. If you “improve the model” you are
working the wrong layer.

### Freeze (do not touch)

k-rate ensemble, TBF ridge, Poisson, WS1c, 4.5-over veto, line floors,
probation, 1/16-Kelly, SharpAPI live path, regular-season-only,
odds-never-in-trainer. Reopen conditions are in the architecture spec
table. None of them are met this week.

Floors are **evidence thresholds**, not ROI maxima. They were set 9/01
on thin-n. The juiced ledger is the first measurement that speaks the
same language as those floors. It is still not a promotion license.

### Work (research / ops — still not live policy)

Done this week: vendor envelopes, juiced attach both years, rejected
candidates, flat-1u vs Kelly arms, featured totals lake.

Still open, ranked by whether they change a money claim:

1. **Fills.** Paper juiced 1u ≠ Novig. Limits, re-quotes, vanish,
   rejected-bet logging. Standing rule: ≥50 real tickets before a
   money-edge claim. This is the only thing that turns +7.3% into a
   bankroll.
2. **Fill-set honesty.** Canonical next-book includes BetRivers. Live
   fills are closer to DK+FD. Report both forever. Do not mix.
3. **Dawn / open carriage.** Skill lives at −12h. SharpAPI may not.
   Owner probe, then maybe an append-only dawn poll. Day-game policy
   is gated on that probe.
4. **Nested juiced v2 post-9/27.** 2025-select / 2026-judge **once**,
   juiced, morning-or-open only, full live stack as one pre-registered
   family. White Reality Check / PBO / DSR on **policy configs** (the
   56-config harness is a snooping surface). Champion rule is not max
   ROI: LCB_95(ROI)>0 on slate-clustered bootstrap, CLV≥0 after vig,
   no single line/side dominating, robustness across books.
5. **Slate correlation.** Totals lake was joined 2026-09-11
(`slate_shock_join.py`): 533 games carry 2+ tickets (1,504 tickets,
1,633 correlated pairs). Per-game / per-side / common-shock caps are
still unbuilt — that is October work. 12u/20u slate caps today
are heuristics, not a risk model.
6. **Stacker stage 2 shadow** if the owner gos. Ties book Brier on
   bettables; ~80% market-following; can compress CLV. Display-only
   until two green weekly confirms, then stage 3 is a separate go.
7. **Envelope-aware first-pitch close.** 12 post-commence “closes”
   already dropped from juiced CLV. Statcast first-pitch vs commence
   is the remaining integrity cut.

### Product (not this season, but this is the north star)

A product is a system that:

1. Has proven **flat-1u** positive EV after vig under a **realistic
   fill scenario** (not optimistic best-book, not BetRivers-soaked
   next-book unless that is actually where you fill).
2. Records actual fills and rejected bets (limits, re-quotes, vanish).
3. Caps correlated exposure (game, team, side, common-shock totals).
4. Keeps kill-switches mechanical (postseason HOLD already is).
5. Hits an SLA (morning board by a published clock — failure banners
   and settle hard-guard already exist).
6. Survives an audit: every ticket reconstructible from raw JSON +
   frozen hashes + policy version.

Until (1)–(3) are true, call it **paper operations with institutional
hygiene**, not a betting product, not a SaaS, not a fund. Legal /
compliance for those is a different company.

The owner’s earlier product instinct (“right charts on Streamlit”) is
subordinate. Charts that should exist someday, wired to artifacts not
notebooks: Today board with veto/offset/opener reasons; deduped equity
+ brake; over/under; CLV; skill vs book from `rescore_cal_report.json`;
weekly pack CIs; juiced 1u vs paper track; shadow stacker. Spec is in
the 2026-09-10 section below. Do not build it.

---

## 4. Where a bigger edge actually is (ranked)

Modeling will not print ROI. Measured levers:

1. **Bet earlier, and fill there.** Same-game +0.044 at open, gone by
   T−5h. Paper edge without fills is not money. Dawn probe is owner.
2. **Stop taking selector-invented tickets.** 4.5 overs (veto live);
   morning edge ≳ 0.20 (we are wrong, not bold); offset-manufactured
   edges. Cap 0.02 and an upper edge bound are selection, not a model.
3. **Unders in the 0.08–0.18 fair band** (≈ 0.05–0.15 juiced). Repeats
   in 2025 and 2026. Live floor 0.12 juiced sits at the back of the
   band — slightly tight, not loose. Do not loosen from 2026 juiced.
4. **Book choice.** DK/FD juiced 1u is a different object from
   next-book. Line-shopping is a real lever, second to model error,
   first among *execution* levers once fills exist.
5. **Fills.** ≥50 real tickets.
6. **Stacker** as calibration overlay, shadow only.

Not on this list: retrains, another floor sweep, promoting harness
+33% fair, 5-minute ticks, featured totals as a K feature.

---

## 5. Clocks (so you do not mix snapshots)

| Name | When | Source | On panel |
|---|---|---|---|
| Friend open | commence −12h / −6h | friend CSV, 2025-03-27 → 2026-07-10, K+outs | `p_friend_open` |
| Paid morning | commence −5h **request**; use vendor ts | Odds API historical event-odds | `p_book_morning` |
| Paid close | commence −5min **request**; 12 are after commence | Odds API historical event-odds | `p_book_close` |
| Featured totals morning/evening | calendar 12:00 ET / 19:55 ET | Odds API historical **sport** odds | `featured_totals.parquet` (not on K panel) |
| Live poll | SharpAPI, whenever the box is awake | `ledger.parquet` / recs | not on universe panel |

Night 19:05 ET → morning ~14:05 ET. Day 13:05 ET → morning ~08:05 ET.
That is why day games are disadvantaged without a dawn poll.

Join keys: `production/ops/market_research/join_keys.py` (`sorted_key`,
`read_consensus_cache`). Research reads the consensus cache; never
re-devig.

---

## 6. File map (what OpenCode actually needs)

### Must-read docs

| File | Role |
|---|---|
| `docs/EXECUTION_BACKLOG.md` | Master work-state. Wins all fights. |
| `docs/reference/opencode_handoff.md` | This briefing. |
| `docs/reference/oddsapi_replay_architecture.md` | How replay must be built. |
| `docs/reference/golden_metrics.md` | Numbers + JSON sources. |
| `docs/reference/experiment_sop.md` | How to run a challenger. §8 is law. |
| `docs/reference/beat_the_books_program.md` | Diagnosis + kill criteria. Modeling closed. |
| `docs/reference/retrain_spec.md` §7 | Pregame retrain CLOSED. |
| `docs/reference/reports/juiced_replay_ledger_2026-09-11.md` | Juiced 1u evidence. |
| `docs/reference/reports/oddsapi_replay_inventory_2026-09-11.md` | Lake inventory, envelopes, quota. |
| `docs/reference/repo_canonical_map.md` | Canonical vs archive. |
| `production/README.md`, `INDEX.md`, `RUNBOOK.md` | How to run the desk. |
| `AGENTS.md` | Pointer table only. |

### Must-know code

| Path | Why |
|---|---|
| `production/odds/odds_board.py` | Live BET/HOLD. |
| `production/odds/poll_odds.py` | Live SharpAPI. |
| `production/ops/kpi_policy.json` | Veto, probation, postseason. |
| `production/ops/market_research/line_floor_policy.json` | Line floors. |
| `src/Python/market.py` | Devig, edge, Kelly 0.0625, CLV. |
| `src/Python/count_layer.py` | `COUNT_LAYER_FAMILY_DEFAULT="poisson"` |
| `src/Python/odds_ledger.py` | Atomic writes, `dedupe_ledger_props`. |
| `production/ops/market_research/juiced_replay_ledger.py` | Juiced 1u measurement. |
| `production/ops/market_research/pull_featured_totals.py` | Totals lake. |
| `production/ops/market_research/pull_oddsapi_historical.py` | Prop lake (do not re-pull). |
| `production/ops/market_research/recover_snapshot_envelope.py` | Vendor clocks. |
| `production/ops/market_research/join_universe.py` / `join_keys.py` | Panel join. |
| `production/ops/market_research/decision_grade_harness.py` | Fair-price folklore; not live. |
| `tests/test_juiced_replay_ledger.py` | Policy helpers + totals clocks. |

### Cite, do not recompute

| Artifact | What |
|---|---|
| `artifacts/odds_log/juiced_replay_report.json` | Juiced 1u + by-book + probation |
| `artifacts/odds_log/juiced_replay_candidates.parquet` | Rejected+taken rows |
| `artifacts/odds_log/rescore_cal_report.json` | Universe Brier/ECE/MCE |
| `artifacts/odds_log/paper_quant_report.json` | 36-day juiced paper Sharpe/DD |
| `artifacts/odds_log/decision_grade_report.json` | Harness (fair, peeked) |
| `artifacts/odds_log/ledger_gate_stacker_report.json` | Stacker on bettables |
| `artifacts/odds_log/correction_audit_report.json` | Offset cap research |
| `artifacts/odds_log/drawdown_brake_latest.json` | CAUTION ×0.5 shadow |
| `docs/reference/reports/weekly_policy_settle_pack_latest.md` | Veto A/B |
| `artifacts/odds_log/universe_panel_live.parquet` | Frozen live-config probs |
| `data/Odds-Historical/theoddsapi/consensus_cache.parquet` | Devigged fair |
| `data/Odds-Historical/theoddsapi/snapshot_envelope.parquet` | Vendor ts |
| `data/Odds-Historical/theoddsapi/featured_totals.parquet` | Slate totals |
| `data/Odds-Historical/theoddsapi/book_lines_pitcher.parquet` | Juiced K/outs/… |

`.cursorignore` excludes `data/`, `artifacts/`, `.venv/`. Do not glob
parquet to “discover” the repo. Paths above are enough.

---

## 7. Allowed vs gated (the contract)

**Always allowed (ops hygiene):**

- Settle open rows. Never `--auto-settle-api` on unstarted games.
- Weekly pack + `ledger_gate_stacker.py`.
- Closeout `pull_regular_season_closeout.py` (K+outs; refuse today/
  future; refuse past 2026-09-28).
- Tests for any change you are actually asked to make. Prefer Polars.
- Snapshot write-back if work state changes.

**Needs owner one-liner (offset cap, edge cap, robust refusal, and totals
join already shipped 2026-09-11):**

- Stacker stage 2 (shadow columns) or stage 3 (drives edge).
- Drawdown brake ×0.5 as live staking (parked 2026-09-11).
- Any further floor / veto / KING / calibrator / Poisson revert.
- Named juiced-driven policy edit (Cursor already refused a blanket
  retune).
- Dawn poll implementation (after owner probe).
- Totals **join** / slate-cap research (lake is pulled; join is new
  science).
- Dashboard v1.
- `make_figures` / PDF.
- Paid −30h K open.

**Refuse even if asked casually:**

- Retrain / Optuna / MLflow (DEFERRED).
- Global floor sweep on 2026 paper or on juiced 2026.
- 5-minute prop ticks.
- Treating FORWARD diary `#66–#120` as a queue.
- Recomputing universe Brier.
- Promoting fair-price harness ROI as a betting slip.
- Mixing SharpAPI live CLV with Odds API juiced 1u as one number.
- Shipping BetRivers-soaked +7.3% as “the” EV while live fills DK+FD.

After any work-state change: update Snapshot PAST / PRESENT / FORWARD /
DEFERRED. New ideas go in Parking Lot. Cite n, Brier/skill, ECE/MCE,
ROI/WR, CLV to a file or report key.

---

## 8. Notebooks vs golden CLV (still true)

Six decision notebooks were refreshed 2026-09-11. They still read
**SharpAPI paper CLV**, not the Odds API panels. Panel-aware notebooks
are after dashboard, not a side quest. Do not drive Streamlit off
`results_dashboard.ipynb`.

Charts that *should* exist someday (cohort-label them): cumulative
realized vs expected PnL; unders carry / overs bleed; edge-decile
elbow; rolling CLV beat-rate. Do **not** put on an operator app:
MAE-vs-ROI scatter, fair-price +62–102%, stacker as live edge.

---

## 9. Parked dashboard spec (do not build)

When unparked, wire to artifacts. Do not re-plot notebooks. Do not
`read_parquet` the 71k panel on every rerun. Canonical money =
`dedupe_ledger_props`.

| Tab | Show | Source |
|---|---|---|
| Today | BET/HOLD/skip + veto/deploy reason + offset share + opener | `recommendations.parquet` |
| Money | Realized vs expected + brake pill | deduped ledger + brake JSON |
| Sides | Over vs under rolling ROI | ledger |
| CLV | Beat-close + mean pp | ledger `clv_pp` |
| Skill | Us vs book Brier/ECE/MCE + 8 lines | `rescore_cal_report.json` |
| Policy | Weekly lanes + CIs | weekly pack JSON |
| Replay | Juiced 1u canonical vs DK+FD vs 2025/2026 | `juiced_replay_report.json` |
| Shadow | `p_stacker` display-only | stacker report |

---

## 10. How to talk to the owner

They are technically strong and will hole-poke nesting, clocks, and
book mix. Be literal. Lead with the number and its lane. Do not invent
a parallel backlog. Do not “just raise the floor” because juiced 2026
looks green. If they want a live change, make them name the file and
the value.

Current owner locks (2026-09-11): next-book canonical; polish-then-stop
on this ledger; totals pulled; live retune refused pending a named
edit. Waiting in parallel, not a queue: offset cap, stacker stage 2,
morning edge cap, NightlyDrift register, dawn probe, fills, push.
