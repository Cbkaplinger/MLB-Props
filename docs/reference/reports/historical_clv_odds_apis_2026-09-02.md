# Historical K-line / CLV odds APIs — research note (2026-09-02)

> Point-in-time evidence for Perplexity / human final decision. **Not** the live work queue — see `docs/EXECUTION_BACKLOG.md`.
>
> Goal: cheapest path to **high-quality pitcher-strikeout open→close (and ideally multi-timestamp) CLV** covering **2025–2026** for the MLB Props paper + backtest.
>
> Repo already uses **SharpAPI** for *live* open/close polling (`SHARPAPI_KEY`, `production/odds/poll_odds.py`). That is **not** the same as a cheap historical archive.

## Verdict (short)

| Priority | Action | Approx cost | 2025? | 2026? | Quality for paper CLV |
| --- | --- | --- | --- | --- | --- |
| 0 | Inventory what you already have under `data/Odds-Open-Close-2025-2026/` | $0 | partial | partial | early-open CSVs only — not full close CLV |
| 1 | Download **SmartStake** Hugging Face `mlb-player-props` (strikeouts included) | $0 | **no** | Mar–Jul only | Excellent minute ticks + grades; incomplete season |
| 2 | Smoke **OddsPapi** free `/historical-odds` for MLB K props (≤3 books/call) | $0 | unclear / likely weak | docs: **since Jan 2026** | Full tick path if coverage real; verify market IDs + US books |
| 3 | **Main play:** one-month **The Odds API** (`the-odds-api.com`) paid plan → pull snapshots → parquet → cancel | **~$30–119** (likely **$59** @ 100k credits) | **yes** (props hist from May 2023) | **yes** | Best depth/price for full 2025+2026 open/close; US books |
| 4 | Optional: PropLine **$99** one-time backfill | $99 | **no** (archive from ~Apr 2026) | partial | Graded close+open CSV; gaps early season / no 2025 |
| SKIP | SharpAPI Enterprise hist | Custom / expensive | unknown | yes (if subscribed) | Nice DX but wrong economics for a one-shot backfill |
| SKIP | OddsBlaze / SportsGameOdds Pro as primary | **$229–499+/mo** | varies | yes | Pro-grade overkill for personal burst |
| CAUTION | `theoddsapi.com` (no hyphen) ≠ `the-odds-api.com` | $99/mo Business | limited | archive often **from May 2026** | Different product; do not buy on name confusion |

**Recommended sequence for cheapest quality:** free SmartStake (2026 slice) → OddsPapi smoke → if 2025 + full-season close still missing → **The Odds API $59 one month**, event historical endpoint, `pitcher_strikeouts`, regions=`us`, **≥2 timestamps** (open + close; ideally game-day morning too) → cache parquet → cancel.

---

## What “best CLV quality” means here

For a defensible manuscript / portfolio CLV claim you want:

1. **Same market** you bet: MLB `pitcher_strikeouts` (alts optional later).
2. **Books you can actually bet** (DK/FD at minimum; Pinnacle/Circa as sharp reference if available).
3. **Decision-time price** (bet / open) **and** **true pre-first-pitch close** (not post-game).
4. Ideally **≥2–3 timestamps** (open, morning-of, close) for line-movement features — not close-only.
5. **Stable player + event IDs** joinable to your ledger / Statcast game_pk.
6. Coverage across **2025 full season + 2026 YTD** (your projection window).

---

## Provider comparison (researched 2026-09-02)

### A. SmartStake / Hugging Face — FREE research dump

- Dataset: [SmartStake/mlb-player-props](https://huggingface.co/datasets/SmartStake/mlb-player-props) (~621M rows, ~901 MB).
- Coverage: **late March 2026 → early July 2026**; markets include **strikeouts**; ~75 books/exchanges (DK, FD, Pinnacle, Kalshi, etc.); outcomes graded.
- Schema: minute ticks (`ts`) + `start_time` → you can compute per-book open = first pre-game quote, close = last `ts < start_time`.
- License: CC BY 4.0 research/education.
- Gaps: **no 2025**; missing late 2026 season; huge download — keep under ignored `data/` after pull.
- **Use:** immediate free 2026 CLV skill study + sharp-book hierarchy; not a full 2025–26 backfill.

### B. OddsPapi — free historical ticks (verify first)

- Endpoint: `GET /v4/historical-odds` with `fixtureId` + ≤3 `bookmakers`.
- Marketing: historical player props on free tier; nested snapshot lists (open→close path).
- Docs note: **“All historical odds data since January 2026 is available.”** → **2025 likely missing**.
- Rate limit: ~5s cooldown per call; 3 books/call → many fixtures to loop.
- **Use:** $0 smoke test for 2026 MLB K market IDs + DK/FD/Pinnacle. Gate: if fixture list or K market thin, do not build pipeline on it.

### C. The Odds API — `the-odds-api.com` (MAIN PAID PLAY)

- Props historical: **from May 3, 2023**, 5-minute snapshots (covers **full 2025 + 2026**).
- Endpoint for props: `/v4/historical/sports/{sport}/events/{eventId}/odds` with `date=` snapshot.
- Official quota (site docs): **10 credits per region per market per event** for historical event odds.
- Market key: `pitcher_strikeouts`; sport: `baseball_mlb`; region: `us`.
- Published plans (site, Sep 2026): **$30 / 20k**, **$59 / 100k**, **$119 / 5M** credits; historical on paid plans.
- Rough math (1 region, 1 market):
  - ~2,430 MLB games/season × 2 seasons ≈ 4,860 events
  - Close-only: 4,860 × 10 ≈ **48.6k credits** → fits **$59**
  - Open + close: ≈ **97k credits** → still ~**$59** (tight) or bump to **$119** if you add a third snapshot or burn credits on event-id discovery
  - Event-id lookup via historical events endpoint also costs credits — budget headroom
- Fits existing mental model from earlier chats; cancel after parquet cache.
- **Use:** canonical paid backfill for paper-grade 2025–2026 CLV.

### D. PropLine — $99 one-time export

- One-time **$99**, 7-day uncapped export: resolved props + open/close, plus tick firehose.
- Archive begins **~April 2026** — **empty before that** → fails 2025 and early 2026 Opening Day.
- Compatible-ish with Odds-API-style schemas (marketing claim).
- **Use:** only if you abandon 2025 and want a cheap graded 2026 mid-season dump; else skip.

### E. SharpAPI (current live vendor) — skip for hist

- Live path already wired (`src/Python/sharp_odds.py`).
- Historical CLV / closing archive: **Enterprise-only** (custom $).
- Pro ($229) / Sharp ($399) do **not** unlock deep historical.
- **Use:** keep free/Hobby for daily board; do **not** buy Enterprise just to backfill.

### F. OddsBlaze

- Marketing: hist CLV/OLV; plans cited ~$29 (delayed) → $249+ realtime → higher for full.
- CrazyNinjaOdds affiliate copy still cites **~$299/mo** entry for serious feeds.
- **Use:** skip for one-shot personal backfill.

### G. SportsGameOdds

- Historical on **Pro ~$499/mo**; per-event object billing.
- **Use:** skip.

### H. SportsDataIO / OddsJam-class

- Warehouse / sales-gated historical props; enterprise pricing.
- **Use:** skip unless employer budget.

### I. Name collision: `theoddsapi.com`

- Separate product advertising Business **$99/mo** with “historical included.”
- Published archive start often **May 2026** and featured markets emphasis — **not** a drop-in for May-2023 prop depth.
- **Do not confuse** with `the-odds-api.com`.

---

## Already in-repo (do not re-buy blindly)

Under `data/Odds-Open-Close-2025-2026/` (ignored by new `.cursorignore`):

- `pitcher_strikeouts_early_open_2025_2026.csv`
- `pitcher_outs_open_2025_2026.csv`

Treat as **early-open** research slices. Before paying anyone, quantify: row count, date span, books, whether closes exist, join rate to ledger. Gaps drive the paid pull.

Live forward CLV continues via SharpAPI open + `close_watcher.py` — historical backfill is a **one-time store**, not a second live poller.

---

## Credit / cost math (The Odds API) — verify on site before buy

Assumptions to re-check on checkout day:

- Historical **event** odds = **10 credits × regions × markets × event** (confirm current docs; some OpenAPI mirrors say 1 — **trust live billing headers**).
- Discovery: historical events list per day/date also consumes credits.
- Books: requesting `regions=us` returns multiple US books in one market charge (region-based, not per-book) — good for DK+FD in one call.
- Strategy: pull **only** `pitcher_strikeouts`; timestamps = first-seen open (~24–30h pre) + morning (~4–6h pre) + last pre-commence close; store raw JSON + normalized parquet under `data/` (ignored).

---

## Perplexity handoff prompt (paste this)

```
You are reviewing a personal MLB pitcher-strikeouts props project.
I need a final recommendation + step-by-step execution checklist for
CHEAPEST high-quality historical CLV data covering 2025–2026.

Constraints:
- Live odds already use SharpAPI (free/Hobby). Do not recommend SharpAPI
  Enterprise unless clearly cheaper than a one-month The Odds API burst.
- Prefer one-time or one-month burst, then cancel; cache to parquet.
- Market: MLB pitcher_strikeouts; books: at least DraftKings + FanDuel;
  want open + close (ideally a third game-day morning snapshot).
- Repo already has partial early-open CSVs in data/Odds-Open-Close-2025-2026/.
- Free candidates already researched: SmartStake HF mlb-player-props
  (2026 Mar–Jul only), OddsPapi hist (docs say since Jan 2026).
- Main paid candidate: the-odds-api.com (NOT theoddsapi.com) historical
  event odds, ~10 credits/region/market/event, plans $30/$59/$119.
- Skip OddsBlaze / SportsGameOdds $299–499 unless you find a cheap hist
  SKU I missed.
- PropLine $99 one-time starts ~Apr 2026 — no 2025.

Please:
1) Confirm or correct which vendor wins on $/quality for FULL 2025+2026.
2) Give a numbered walkthrough: free verification → paid pull → schema →
   cancel → how to join to an existing ticket ledger.
3) Call out gotchas (credit burn on event-id discovery, close vs in-play,
   book coverage gaps, name-collision APIs).
4) Propose a minimal pull script outline (Python + Polars) without
   over-engineering.
```

---

## Sources checked (2026-09-02)

- https://the-odds-api.com/historical-odds-data/
- https://the-odds-api.com/#pricing
- https://oddspapi.io/en/docs/get-historical-odds
- https://prop-line.com/historical-backfill
- https://huggingface.co/datasets/SmartStake/mlb-player-props
- https://docs.sharpapi.io/en/pricing/
- https://docs.sharpapi.io/en/api-reference/historical-clv/
- https://sharpapi.io/pricing
- Third-party comparisons (SharpAPI blog, JediBets, OddsBlaze profiles) — treat prices as soft; verify on vendor sites

---

## Repo handoff already done (Lenovo → Mac)

- `.cursorignore` + `.clineignore` — exclude data/artifacts/venv/parquet/binaries/media
- `.cursorindexingignore` — fixed lowercase `data/` paths
- `.cursor/rules/agent-context.mdc` — open backlog + canonical map first
- `AGENTS.md` — Mac handoff pointer block
