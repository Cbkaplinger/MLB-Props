# Historical CLV Backfill — Full Execution Plan (2026-09-08)

> Status: APPROVED structure, AWAITING $59 subscription. Master work-state stays
> `docs/EXECUTION_BACKLOG.md`; this doc is the stable reference the backlog points to.
> Standing rules apply throughout: post hoc only, chrono-safe splits, post-freeze
> window eval-only, no live policy edits without sign-off.

## 0. Objective

Buy once, analyze for months. One paid pull of **MLB pitcher-strikeout book
CLOSES, 2025 full season + 2026 to date**, joined to owned opens (26k K rows,
friend 12h) and owned outcomes (Statcast/graded), to answer: is the 4.5-over
bleed a probability problem or a selection problem — and to re-estimate floors
and calibration on honest data.

## 1. Scope (locked)

- Markets, pull #1 (DECISION PENDING — see §3): `pitcher_strikeouts` closes
  ONLY ($59, ~45k credits) OR the 4-market bundle K/outs/batter-hits/batter-walks
  ($119/5M, ~185k credits). Not decided until user picks.
- Seasons: 2025 full (incl. postseason), 2026 regular to pull date (incl. postseason if scheduled).
- Regions: `us` ONLY (DK/FD/MGM/Bovada/BetOnline). `us2` (ESPN/Fliff/HardRock)
  costs a full doubling in credits — NOT worth marginal books (see §3).
- Snapshots: close = last pre-commence. NO morning snapshot (5M plan has headroom
  to add it later same month if analysis demands).
- Overage/upgrade reality: quota hard-stops at 429, no surprise billing (verify on
  billing page). Mid-month upgrade IS possible but NOT pro-rated down — $59→$119
  costs ~$178 total, so the "cheap then upgrade" path is the WORST economics. Pick
  the right plan up front. `us2` excluded by math, not taste.

## 2. Vendor (locked)

`the-odds-api.com` (hyphen). Plan decided by §3 math: $59/100k (K-only) or
$119/5M (4-market bundle). One month, cancel same week.
NOT `theoddsapi.com` (no 2025 archive), NOT PropLine (no 2025), NOT OpticOdds
(rolling 2-month), NOT SharpAPI Enterprise, NOT SportsDataIO (sales-gated $$$).
Free complements (no spend): Kalshi KXMLBKS ladders (sharp reference, built),
SmartStake HF (batter markets only — parked for winter batter work).

## 3. Credit math (verified free; trust billing headers over docs)

- Cost: 10 credits × REGIONS × markets × events × snapshots. Regions MULTIPLY:
  `us` alone = 1×, `us`+`us2` = 2×. Correction 2026-09-08: an earlier note said
  us+us2 rides free — it does not. Marginal books (ESPN/Fliff/HardRock) cost a
  full doubling; they are NOT worth it. Pull `us` only (DK/FD/MGM/Bovada/BetOnline).
- Events: ~2,430 (2025 incl. postseason) + ~2,000 (2026 to date) ≈ 4.4k.
- Per market per snapshot (`us` only): ≈ 44k. Discovery (event-ID listing) ≈ 1–6k.
- Overage policy: quota hard-stops (429, no surprise billing — confirm on the
  billing page at buy time). Script hard-stops at 10% floor regardless.

## 4. Book list + juiced-book doctrine

Pull everything `us` returns (DK/FD/MGM/Bovada/BetOnline — bundled, no per-book
cost). `us2` excluded (ESPN/Fliff/HardRock) — a full credit doubling for marginal
books, not worth it. Fliff/HardRock juice is therefore NOT in scope; if a future
need for public-flow signal appears, a targeted one-off is possible later.
1. Devig each book FIRST (multiplicative for 2-way props) — vig-stripping removes
   their margin; a juiced line still carries the same fair estimate, just noisier.
2. Consensus = median of devigged probs (robust to outliers), book-count as confidence.
3. Sensitivity: rerun headline numbers ex-any single book; report both if they differ.
4. Cross-book disagreement flags feed bugs (QA, not alpha).

Labels (non-negotiable): consensus-beating = "beat the soft books", never true
probability. Pinnacle absent for MLB props on all US regions (verified 2026-09-08);
Kalshi = sharp anchor (exchange ≠ book, label it); Novig fills (`real_bets`) = money truth.

## 5. Timestamp doctrine (write once, cite in paper review)

- Close = last quote with timestamp strictly before that game's actual first pitch.
- Consensus timestamp = median of contributing book timestamps (report spread).
- Kalshi anchor = last trade ≤ MLB-scheduled first pitch (conservative; rain-delay
  late steam sacrificed, leakage impossible).
- Anything violating this is not called a close anywhere in analysis.

## 6. Pull protocol (mechanical, in order)

1. User: log in → billing → $59/100k → pay → confirm dashboard shows paid plan.
   Calendar-note the cancel date NOW. Screenshot the plan page.
2. Agent: `estimate` (validates key + prints tier math), then `pull --snapshots close`
   2025 season first, then 2026. Watch `x-requests-remaining` every 100 events.
3. Raw JSON cached forever under ignored `data/Odds-Historical/theoddsapi/`
   (re-normalization never re-spends). Normalize → `book_lines.parquet`.
4. User: cancel auto-renew same week. Key stays (free tier for plumbing).
5. Failure modes: floor-hit ⇒ stop, report, resume-or-upgrade decision (never silently
   continue); 403 mid-pull ⇒ plan lapsed, halt; schema drift (new outcome keys) ⇒
   extend normalizer, re-run normalize only.

## 7. Join + analysis plan (pre-registered)

Join keys: normalized name + game_date + line (+book where available).
Accent-fold + 4-entry alias map already handle Jesús/Joey/Mike-class mismatches;
unmatched = reported, never forced.

Pre-registered cells (everything else exploratory until the weekly pack confirms):
1. 4.5-over: Brier skill vs consensus-close AND vs Kalshi; WR/ROI/CLV.
2. 3.5-over and 5.5-under: same panel (probation + strength pockets).
3. Calibration challenger: RAW vs Platt-20260803 vs isotonic-20260821 on a held-out
   chrono split. Champion freezes; promotion needs sign-off + revert path.

Secondary (decision-useful, not gating): steam segmentation (edge in steam games =
timing strategy, not modeling edge); open→close decomposition (opener-beating vs
timing); volume/book-count sensitivity; per-regime (Platt/iso/raw-era) splits.

## 8. Expansion plan (pull #2, when K work is digested)

- Verify exact market keys live first (`pitcher_outs`, batter hits/walks keys —
  unused keys still burn per-market credits).
- Same protocol: closes-first, raw cached, cancel same week.
- PropLine $99 graded dump stays the fallback if books-only proves insufficient
  (it bundles outcomes; 2026-only).

## 9. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Credit overrun strands pull | closes-first order + 10% floor + live header watch |
| Subscription renews | cancel same week; calendar note at buy time |
| Line-movement lookahead | timestamp doctrine §5; Kalshi pre-pitch anchor |
| Overfit via cell-slicing | pre-registered cells §7; DSR culture; weekly-pack confirmation |
| Live-policy contamination | standing rules; challenger protocol, sign-off gate |
| Pinnacle envy | accepted gap; Kalshi anchor + labeled consensus instead |

## 10. Definition of done

Raw JSON cached + normalized parquet + join-rate report + side-by-side skill
(Kalshi/book/model) + 4.5-over verdict + floor/calibration recommendations +
subscription cancelled. Then Phase 3 (README/docs sweep, metric cleanup, brake).
