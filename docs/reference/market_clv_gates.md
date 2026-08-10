# Market / CLV gates (pre-registered)

**Status:** locked operating protocol for the betting product layer  
**Scope:** odds never enter the strikeout trainer  
**Code:** `src/Python/market.py`, `skill_stats.py`, `odds_ledger.py`, `odds_close.py`, `odds_board.py`, `sharp_odds.py`  
**Ops:** `production/odds/odds_board.py`, `poll_odds.py`, `close_watcher.py`, `grade_odds_ledger.py`  
**Protocol UI:** `production/notebooks/daily_projections.ipynb` (morning board + CLV skill tracker)  
**Skill dashboard:** `production/notebooks/results_dashboard.ipynb` (Sections 11-20, CLV skill suite + appendices) — see `docs/research/notebook_change_log.md`

## Separation of concerns

| Layer | Role | Odds allowed? |
|---|---|---|
| Strikeout stack (`expected_K`, raw `p_over_*`) | Predict baseball | **No** |
| Post-hoc calibrator (`p_over_*_cal`) | Honesty map on prop probs (Platt) | No — still baseball layer |
| Market math | De-vig, edge, Kelly, units, CLV | Compare / size / grade |
| `src/Python/skill_stats.py` | z-test / BCa / stake-weighted / rolling-SE on the CLV ledger | Yes (read-only on the ledger) |
| `artifacts/odds_log/ledger.parquet` | Durable paper tickets | Yes |
| Accept/deny curve | Exploratory until n_clv ≥ 150 at floor ≥ 12% + pre-registered held-out check | Yes (on ledger only) |

Edge uses **calibrated** `p_model` when `p_over_*_cal` is logged
(`odds_board.p_model_over_for_line`). Apparent edges may shrink vs raw — that is
expected; do **not** raise a current floor even higher from that shrinkage alone — a higher floor must clear a held-out time split, per the 2026-08-06 floor-freeze precedent.
See `docs/research/prob_calibration_findings.md`. The same caution applies in
reverse: do **not** lower the 12% floor from calibrator-induced edge shrinkage
either — see `docs/research/floor_freeze_log.md` (2026-08-06 reaffirmation).

Opening / bet-time lines are **compared** to model probabilities.  
Closing lines **grade** CLV. Final K grades win/loss. Neither trains LightGBM.

## Locked formulas

- **De-vig (multiplicative):** fair probs from over/under American pair  
- **Edge:** `p_model − p_mkt` on bet side  
- **Kelly fraction:** **⅛ Kelly** (`0.125`) as of the 2026-08-06 Kelly freeze
  (was 0.25 prior; the sizing halved while the CLV skill gate stays
  INCONCLUSIVE — see *§ Decision rules*). Code: `market.DEFAULT_KELLY_FRACTION`.
- **CLV (pp):** `p_mkt(close, side) − p_mkt(bet price)` on the **same ticket**  
- **Unit anchor:** 1u = **⅛ Kelly on 12% edge @ −110** ≈ **3.15% of bankroll**
  (the pre-freeze "8% @ −110 ≈ 4.2%" wording was the 0.08 floor /
  quarter-Kelly value and is kept here only as a historical note; the active
  anchor is `market.unit_anchor_kelly_frac()` re-computed from
  `DEFAULT_EDGE_FLOOR=0.12` / `DEFAULT_KELLY_FRACTION=0.125`).
  - `bankroll = unit_dollars / anchor_frac` (recompute if typical odds ≠ −110)  
  - `units = kelly_frac_stake / anchor_frac` (0 if edge < floor)

Detail tables may show **both** DK and FD. Skill stats / curves **dedupe** to
one ticket per `(game_date, pitcher, line)` — keep the **highest-edge** book
(same rule as `odds_board` best-book). Ties prefer same-book close (`ok`) over
`ok_cross_book`.

## Pre-registered decision rules

| Gate | Rule |
|---|---|
| Edge floor | Bet only if `edge ≥ 0.12` (raised from 0.08 on 2026-08-06, reaffirmed **12%** the same day on the resolved ledger — see *Floor freeze* below and `docs/research/floor_freeze_log.md`) |
| Unit default | **$50** → implied BR ≈ **$1,590** at the active 12% / ⅛-Kelly anchor (`market.unit_anchor_kelly_frac()` ≈ 0.0315) |
| Kelly fraction | **0.125** (eighth-Kelly; halved from 0.25 on 2026-08-06 while CLV skill gate is INCONCLUSIVE) |
| Min sample | **n_clv ≥ 150** settled props with CLV at **floor ≥ 12%** (deduped; BET + skip both count) before any floor/Kelly move; see `floor_freeze_log.md` for the stopping rule |
| Skill bar | Mean `CLV_pp > 0` with **BCa** bootstrap CI excluding 0 (`src/Python/skill_stats.py:bootstrap_bca_ci`; percentile bootstrap is biased at the per-band n≈10-40 and was retired for this purpose) |
| Skill companions | (a) win-rate vs 0.524 break-even at the same band, and (b) `clv_pp` pseudo-ROC AUC > 0.5 (`production/notebooks/results_dashboard.ipynb` §11/§16) |
| Real bankroll | Only after the skill bar AND the win-rate vs break-even gate clear on the live ledger together |
| Threshold sweep | **Exploratory only** until n_clv ≥ 150; floor freezes are pre-registered and recorded in `docs/research/floor_freeze_log.md`. Never crown max-ROI on one sample — see *Recursive floor-rediscovery* below |

### Floor freeze — 2026-08-06 (0.08 → 0.12, reaffirmed 0.12 same day)

Single-sample decision on the live ledger, not a held-out time split. Logged
here as one-shot protocol deviation, not a precedent. Reviewed the same day
against the resolved ledger (ledger SHA-256
`cfddcf674c20da314fab1243c52fa2a637e875cec3c09ce825b8ebe60ac49e37`, 330 rows
/ 199 settled / 72 settled+CLV at floor≥12%) and reaffirmed — see
`docs/research/floor_freeze_log.md` for the auditable record (the freeze log
owns the canonical cell-hash + stopping rule going forward; this section
keeps the prose narrative).

- **Trigger:** n_clv=125 over 120 settled-flat bets (past the n≥100 precondition),
  flat-1u ROI sweep in `production/notebooks/results_dashboard.ipynb` Section 10.
- **Evidence:** flat-1u ROI at floor=8% = **−7.03%** over 70 settled (structurally
  losing segment visible only after lifting the implicit `stake>0` filter);
  flat-1u ROI **turns positive at floor=12% = +1.68%** over n=47 settled; flat
  win-rate crosses 0.50 at the same point; CLV positive across all edge bins
  through floor=23% (CI widens above 18% but mean stays >0 through 23%).
- **Counter-evidence noted:** CLV bootstrap CI at the overall level is still
  (−0.30, +1.36) — INCONCLUSIVE on the skill bar. Floor change is a sizing
  decision (which bets to fire), separate from the skill-bar judgment.
- **Same-day reaffirmation (2026-08-06, end-of-session):** the prior in-chat
  recommendation to *lower* the floor from 12% to 6-8% was driven by stale
  cell output (CLV +0.66–0.72pp at 6-8% vs an n=67 ledger). Re-running
  n-needed math on the resolved ledger (n=199 settled / 217 candidate
  ledger-prompt numbers) gives **floor ≥ 6% needs ~620, floor ≥ 8% ~375,
  floor ≥ 12% ~655** to get a CLV CI that excludes zero at these effect
  sizes — vs the 130-190 claimed in the stale read. The argument to lower is
  fundamentally invalidated, not cosmetically. Reviewed evidence on the
  resolved ledger:
  - **BCa CLV CI at floor ≥ 12%**: `[-0.30, +1.78]` — **includes zero**,
    so the skill bar remains INCONCLUSIVE; **hold** is correct.
  - **Win-rate at floor ≥ 12%**: `0.528` — barely clears 0.524 break-even,
    but does not discriminate on its own.
  - **Two-proportion z-test** on `clv ≥ +1.0pp` (n=54, win-rate 0.519) vs
    `clv < +1.0pp` (n=145, win-rate 0.379): `z=+1.77, p=0.077` —
    directionally the strongest single piece of evidence in the ledger,
    but **not yet α=0.05**. State it precisely.
  - **Stake-weighted CLV** (§14): `+0.262pp` vs equal-weighted `+0.471pp`;
    big-Kelly bets drag CLV **down 0.21pp** — the sizing filter is currently
    amplifying the less-skillful bets. Materially undercuts any escalation
    case until it reverses.
  - **Pseudo-ROC AUC** (§16): `0.553` — real but weak.
- **Re-freeze rule:** hold 12% until **n_clv ≥ 150** at floor ≥ 12% is reached
  (3-4 weeks at the current grading rate), at which point evaluate
  **simultaneously**: (a) BCa CLV CI at floor ≥ 12% excluding zero, AND
  (b) win-rate at floor ≥ 12% > 0.524. Either alone is insufficient. At that
  checkpoint, re-sweep on a held-out window (pre-freeze rows vs post-freeze
  rows) and update the registry only if the held-out sweep disagrees with
  12%. **Do not** do another single-sample floor bump — that's the pattern
  this protocol exists to prevent.
- **Pre-registered next-50-bet checkpoint:** the decision rule above is
  recorded as a frozen artifact at
  `artifacts/odds_log/next_50_checkpoint.json` (timestamp + ledger SHA-256 +
  universe-as-of counts + the full `prereg_rule` dictionary) by
  `production/notebooks/results_dashboard.ipynb` §18b. The future audit reads the JSON
  to assert the "next 50 settled bets at the 12% floor" were chosen from bets
  unsettled *as of this snapshot*, not a re-fitted slice. This is the actual
  fix for "recursive floor-rediscovery" — see that heading below.
- **Logging unchanged:** all quotes (positive-edge, regardless of passes_floor)
  are still written to the ledger and CLV'd by `close_watcher.py`. The flat-1u
  sweep stays policy-blind via `bet_price + result`, so we can detect whether
  12% in turn becomes too low.

### Kelly freeze — 2026-08-06 (0.25 → 0.125)

Halved stakes until the CLV skill gate clears (CI excludes 0). At that point
revert to ¼ Kelly. This is a volatility-tolerance / edge-estimation hedge, not
a skill judgment — the model could be sharp and ⅛ Kelly is still the right
sizing while CI includes zero.

## Daily machine loop

```text
Morning
  1. refresh_statcast → refresh_features --skip-training → log_projections
  2. grade_projections --all-logged --preferred-only
       (--exclude-abbreviated --exclude-out-of-support when grading MAE)
  3. odds_board --unit 50
       (BET-only terminal; full slate → recommendations.parquet;
        prints preferred_missing_quote when DK/FD have no K line)
  4. poll_odds --snapshot open --unit 50
       (REPLACES unclosed same-day tickets — first lock of the day)
  5. grade_odds_ledger --status
  6. Open production/notebooks/daily_projections.ipynb (optional human board)

Catch-up (late markets)
  poll_odds --snapshot open --append --unit 50
  Never re-run open WITHOUT --append after the morning lock.

Near first pitch
  close_watcher.py   (T−15m…T+5m; PC awake)
  or poll_odds --snapshot close

After finals
  grade_odds_ledger --auto-settle-api --status --curve

Weekly / at n_clv ≥ 150 at floor ≥ 12%
  Inspect `production/notebooks/results_dashboard.ipynb` Sections 11-20:
    §11 CLV reliability+relaibility.parquet + two-proportion z-test
    §12 band-discrete flat-1u ROI + edge_band_discrete.parquet (BCa CIs)
    §13 rolling 30-bet CLV with ±2 SE ribbon (day-stability check)
    §14 stake-weighted CLV with BCa CI (Kelly-sizing check)
    §15 per-band CLV distribution histograms
    §16 pseudo-ROC of clv_pp≥t as a classifier of result=win (AUC)
    §17 (p_market, p_close) outcome-pairing scatter
    §18a BCa-CLV floor sweep (authoritative — clv_floor_bca.parquet)
    §18b pre-registered next-50-bet checkpoint (next_50_checkpoint.json)
  Floor frozen at 12% as of the 2026-08-06 freeze+reaffirmation
  (see docs/research/floor_freeze_log.md for the canonical record)
```

SharpAPI free tier = DraftKings + FanDuel (60s delay). Keep local edge/Kelly
math; SharpAPI +EV is sharp-vs-soft, not model-vs-book.

## How plays are tracked

| Artifact | Role | Keeps sub-12%? |
|---|---|---|
| `artifacts/projection_log/projections.parquet` | Model board (xK, `p_over_2_5`…`9_5`) — no book prices | n/a |
| `artifacts/odds_log/recommendations.parquet` | Today’s model × live lines — **overwritten** each board run | **Yes** (full slate) |
| `artifacts/odds_log/ledger.parquet` | Durable tickets from `poll_odds --snapshot open` | **Yes** (BET + skip + OOS) |
| Close / settle / `--curve` | Fill CLV + win/loss; sweep edge floors | Needs full ledger |

**Morning UX:** `odds_board` prints BET (≥12%, in-support) only; writes full slate.  
**Skill loop:** open → tip-window close → settle → `--curve` on **deduped props**.  
The accept/deny curve is meaningless unless skips (edge < 8%) are logged and CLV’d too.

**CLV vs win/loss:** positive CLV means you beat the close on price; it is not
the same as winning the bet. Grade both.

## Accept/deny curve

For thresholds c = 0%, 1%, … 20%:

- keep bets with `edge ≥ c`  
- plot n(c), ROI(c), mean CLV(c)  
- use BCa bootstrap CI on CLV (`src/Python/skill_stats.bootstrap_bca_ci`) —
  percentile CIs are biased and too narrow at the per-band n≈10-40 and were
  retired for the authoritative Section 18a sweep

**Freeze rule:** choose c on an earlier window only; report later window untouched.  
Operate at **12%** as of the 2026-08-06 floor freeze + same-day reaffirmation
(see *Floor freeze* above); re-freeze only at the **n_clv ≥ 150** checkpoint
after pre-freeze-vs-post-freeze held-out agreement — never on a single-sample
sweep.

The pre-registered next-50-bet decision rule lives at
`artifacts/odds_log/next_50_checkpoint.json` and is written by `production/notebooks/results_dashboard.ipynb`
§18b. It is the operational anchor against the **recursive floor-rediscovery**
pattern: the future audit can assert the "next 50 settled at floor=12%" were
chosen from bets unsettled at the snapshot ledger SHA-256, not a re-fitted
slice.

### Recursive floor-rediscovery

The disease this entire 2026-08-06 dashboard batch is designed to kill.
Symptom pattern (visible in the prior in-chat session): a reviewer cites a
single ~120-bet window, sees positive ROI at a band below the active floor,
argues "lower the floor" — then immediately sees a stale cell output, builds
a sample-size n-needed estimate off the stale effect size, and recommends a
move. The resolved ledger invalidates the move; the original argument was
variance layered on stale output. Sections 11-20 strip every step where that
kind of slippage can re-emerge:

- §11 + §16 turn the 53.8%/39.0% one-shot z-test into a persistent,
  monotonicity-checkable, AUC-augmented artifact.
- §12 flags sub-floor bands with positive ROI as "DO NOT use this band's ROI
  to argue for lowering the floor".
- §14 (stake-weighted) and §13 (rolling 30-bet) expose metrics the
  equal-weighted cumulative sweep provably hides.
- §18a replaces percentile CIs with BCa specifically because percentile CIs
  would falsely sequence "real edge at floor ≥ 20%" when the per-band n
  is tiny.

## Artifact layout

```text
artifacts/odds_log/ledger.parquet              # durable tickets (gitignored)
artifacts/odds_log/recommendations.parquet     # today’s board (overwrite)
artifacts/odds_log/recommendations.html
artifacts/odds_log/threshold_curve.parquet     # last exploratory sweep
artifacts/odds_log/last_ledger.json
artifacts/odds_log/close_watcher.log
artifacts/odds_log/clv_reliability.parquet    # §11 weekly decile calibration
artifacts/odds_log/edge_band_discrete.parquet  # §12 per-[f,f+1) band table (BCa CIs)
artifacts/odds_log/clv_floor_bca.parquet       # §18a authoritative BCa floor sweep
artifacts/odds_log/next_50_checkpoint.json     # §18b pre-registered decision rule + SHA-256
artifacts/projection_log/                      # model boards + graded.parquet
```

`artifacts/` is gitignored — never commit ledgers or API dumps. The
`clv_reliability`, `edge_band_discrete`, `clv_floor_bca`, and
`next_50_checkpoint` artifacts are written by
`production/notebooks/results_dashboard.ipynb` Sections 11-20 — see
`docs/research/notebook_change_log.md` for the section-by-section inventory.

## Tracking fields (tip vs open/close)

| Column | Meaning |
|---|---|
| `logged_at_utc` | When the open/bet-time quote was written |
| `event_id` / `event_start_time_utc` | SharpAPI event + scheduled tip (UTC) |
| `minutes_to_tip_at_open` | Tip − open timestamp (minutes) |
| `closed_at_utc` | When close prices were filled |
| `minutes_to_tip_at_close` | Tip − close timestamp |
| `close_status` | `ok` \| `ok_cross_book` \| `unavailable` \| null |

**Open definition:** first `--snapshot open` for that slate day (replace
unclosed). Catch-up = `--append` only. One clean morning open + optional
appends — no stacked replace re-runs.

## OOS / abbreviated (sizing + grades)

| Gate | Rule |
|---|---|
| Pregame OOS | `projected_tbf < 12` or `expected_K < 1.5` or `days_rest ≥ 120` → units 0 / OOS |
| Abbreviated outing | `actual_PA < 9` → exclude from projection MAE when flagged |

## Build sequence status

1. ~~Pure math + gates~~  
2. ~~Manual dry-run / line shopper~~  
3. ~~Ledger + unit sizing + threshold curve tooling~~  
4. ~~Full-slate SharpAPI open logging (idempotent + tip timestamps)~~  
5. ~~Close watcher + settle tooling (`--auto-settle-api`)~~  
6. ~~Morning notebook + prop-deduped CLV skill tracker~~  
7. Catch-up opens (`--append`) + preferred_missing_quote hygiene (ops discipline)  
8. Nightly settle cron + always-on host  
9. n_clv ≥ 150 at floor ≥ 12% → pre-registered BCa-CLV / win-rate checkpoint
   (§18a / §18b, `next_50_checkpoint.json`) — exploratory curves are advisory
   only; floor moves are pre-registered in `docs/research/floor_freeze_log.md`  
10. Real bankroll only if CLV skill bar clears AND win-rate clears 0.524 at
    the same checkpoint  
11. Dashboard Sections 11-20 — **done 2026-08-06** (CLV skill suite:
    reliability+z-test, band-discrete, rolling, stake-weighted, histograms,
    pseudo-ROC, outcome-pairing, BCa sweep, pre-registration); see
    `docs/research/notebook_change_log.md`
