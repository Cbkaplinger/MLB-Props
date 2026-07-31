# Market / CLV gates (pre-registered)

**Status:** locked operating protocol for the betting product layer  
**Scope:** odds never enter the strikeout trainer  
**Code:** `src/Python/market.py`, `src/Python/odds_ledger.py`  
**Ops:** `production/log_odds_quotes.py`, `production/grade_odds_ledger.py`

## Separation of concerns

| Layer | Role | Odds allowed? |
|---|---|---|
| Strikeout stack (`expected_K`, `p_over_*`) | Predict baseball | **No** |
| Market math | De-vig, edge, Kelly, units, CLV | Compare / size / grade |
| `artifacts/odds_log/ledger.parquet` | Append-only ticket ledger | Yes |
| Accept/deny curve | Exploratory until n≥100 + time split | Yes (on ledger only) |

Opening / bet-time lines are **compared** to model probabilities.  
Closing lines **grade** CLV. Final K grades win/loss. Neither trains LightGBM.

## Locked formulas

- **De-vig (multiplicative):** fair probs from over/under American pair  
- **Edge:** `p_model − p_mkt` on bet side  
- **¼ Kelly:** `0.25 × (p×decimal − 1)/(decimal − 1)`  
- **CLV (pp):** `p_mkt(close, side) − p_mkt(bet price)`  
- **Unit anchor:** 1u = ¼ Kelly on **8% edge @ −110** ≈ **4.2% of bankroll**  
  - `bankroll = unit_dollars / 0.042` (recompute if typical odds ≠ −110)  
  - `units = quarter_kelly_frac / anchor_frac` (0 if edge &lt; floor)

## Pre-registered decision rules

| Gate | Rule |
|---|---|
| Edge floor | Bet only if `edge ≥ 0.08` |
| Unit default | **$50** → implied BR ≈ **$1,190** |
| Kelly fraction | **0.25** |
| Min sample | **n ≥ 100** settled **forward** ledger bets before judgment |
| Skill bar | Mean `CLV_pp > 0` with bootstrap CI excluding 0 |
| Real bankroll | Only after skill bar clears on the live ledger |
| Threshold sweep | **Exploratory only** until n≥100; freeze a new floor via **time split** or walk-forward — never crown max-ROI on one sample |

## Daily machine loop (what you do)

```text
Morning
  1. Refresh slate: production/run_daily.py  (or score_slate + log_projections)
  2. python production/odds_board.py --unit 50 --open-html
     (preferred × live DK/FD lines × edge × units — primary morning view)
  3. python production/poll_odds.py --snapshot open --unit 50
     (idempotent: one open ticket per game_date×player×book×line;
      stores logged_at_utc, event_id, event_start_time_utc, minutes_to_tip_at_open)

Near first pitch
  4. Leave running after morning open (PC awake):
       python production/close_watcher.py
     or:  .\production\run_close_watcher.ps1
     Closes tickets when tip is within T−15m…T+5m (Free-tier DIY close).
     One-shot fallback: python production/poll_odds.py --snapshot close

After finals
  5. python production/grade_odds_ledger.py --settle "Name,YYYY-MM-DD,K"
     or --auto-settle-api when game_pk/pitcher present

Weekly / at n≥100
  6. python production/grade_odds_ledger.py --curve --status
  7. Inspect threshold curve; do NOT change 8% until a planned freeze
```

SharpAPI free tier = DraftKings + FanDuel (60s delay). Keep local edge/Kelly math;
SharpAPI +EV is sharp-vs-soft, not model-vs-book.

## How plays are tracked (model vs market)

| Artifact | Role | Keeps sub-8%? |
|---|---|---|
| `artifacts/projection_log/projections.parquet` | Model board only (xK, `p_over_*`) — no book prices | n/a |
| `artifacts/odds_log/recommendations.parquet` | Today’s model × live lines (edge/units) — **overwritten** each board run | **Yes** (full slate) |
| `artifacts/odds_log/ledger.parquet` | Durable paper tickets from `poll_odds --snapshot open` | **Yes** (BET + skip + OOS) |
| Close / settle / `--curve` | Fill CLV + win/loss; sweep edge floors for the elbow | Needs full ledger |

**Morning UX:** `odds_board` prints BET (≥8%, in-support) only; writes full slate.  
**Skill loop:** `poll_odds open` → `poll_odds close` → settle → `grade_odds_ledger --curve`.  
The accept/deny curve is meaningless unless skips (edge &lt; 8%) are logged and settled/CLV’d too.

## How plays are tracked (model vs market)

| Artifact | Role | Keeps sub-8%? |
|---|---|---|
| `artifacts/projection_log/projections.parquet` | Model board only (xK, `p_over_*`) — no book prices | n/a |
| `artifacts/odds_log/recommendations.parquet` | Today’s model × live lines (edge/units) — **overwritten** each board run | **Yes** (full slate) |
| `artifacts/odds_log/ledger.parquet` | Durable paper tickets from `poll_odds --snapshot open` | **Yes** (BET + skip + OOS) |
| Close / settle / `--curve` | Fill CLV + win/loss; sweep edge floors for the elbow | Needs full ledger |

**Morning UX:** `odds_board` prints BET (≥8%, in-support) only; writes full slate.  
**Skill loop:** `poll_odds open` → `poll_odds close` → settle → `grade_odds_ledger --curve`.  
The accept/deny curve is meaningless unless skips (edge &lt; 8%) are logged and settled/CLV’d too.

## Accept/deny curve (how to think)

For thresholds c = 0%, 1%, … 20%:

- keep bets with `edge ≥ c`  
- plot n(c), ROI(c), mean CLV(c)  
- use bootstrap CI on CLV/ROI  

**Freeze rule:** choose c on an earlier window only; report later window untouched.  
Until then, operate at **8%**.

## Artifact layout

```text
artifacts/odds_log/ledger.parquet           # tickets
artifacts/odds_log/threshold_curve.parquet  # last exploratory sweep
artifacts/odds_log/last_ledger.json
artifacts/projection_log/                   # model boards (no book prices)
```

## Tracking fields (tip vs open/close)

| Column | Meaning |
|---|---|
| `logged_at_utc` | When the open/bet-time quote was written |
| `event_id` / `event_start_time_utc` | SharpAPI event + scheduled tip (UTC) |
| `minutes_to_tip_at_open` | Tip − open timestamp (minutes; negative if after tip) |
| `closed_at_utc` | When close prices were filled |
| `minutes_to_tip_at_close` | Tip − close timestamp |

**Open definition:** first / replaced `--snapshot open` for that slate day.
Re-running open **replaces** unclosed same-day tickets (use `--append` to keep
old keys). One clean open set per date — no stacked morning re-runs.

## Build sequence status

1. ~~Pure math + gates~~  
2. ~~Manual dry-run / line shopper~~  
3. ~~Ledger + unit sizing + threshold curve tooling~~  
4. ~~Full-slate SharpAPI open logging (idempotent + tip timestamps)~~ ← you are here  
5. ~~Close + settle discipline (manual → tip-aware watcher)~~ ← watcher shipped  
6. Nightly settle cron + always-on host discipline  
7. n≥100 → exploratory curve → time-split freeze  
8. Real bankroll only if CLV gate clears  
