# EXCLUSION_LEDGER — market-eval-v1 sequential exclusion ledger (C2)

**Date:** 2026-10-14. Machine-readable source:
`outputs\verification\exclusion_ledger.json` (regenerate with
`python verify_ledger.py`). Start counts and contract counts are tracked
SEPARATELY. All stages reconcile exactly.

## Start-level ledger (cohort: pregame-pa-ext-v1 payload, 2024-07-01..2025-09-28)

| # | Stage | Starts | Excluded here | Rule |
| -- | --- | ---: | ---: | --- |
| 0 | original_cohort | **7,194** | — | payload starts (7,194) |
| 1 | identity_resolved | **7,132** | 62 | pitcher MLBAM id absent from `player_id_map` |
| 2 | event_matched | **6,838** | 294 | resolved start with NO archive event for the pitcher within +/-1 day (vendor UTC vs ET date window); **v1 folded these away silently — C2 discloses them** |
| 3 | clock_qualified (eligible) | **6,813** | 25 | doubleheader-ambiguous (vendor_game_date, pitcher) keys (54 keys; 25 starts); no game_pk in envelope, no team labels in payload — unresolvable, excluded |
| 4 | with_actionable_quote | **6,647** | 166 | >=1 pre-cutoff, predictor-aware, non-closing quote (Tier A: quote_ts < first_pitch_ts; Tier B: snapshot != close; both >= predictor_available_ts) |
| 5 | usable_paired_contracts | **6,643** | 4 | >=1 (line, book, clock) quoting BOTH sides in the actionable set (mostly alternate-market-only coverage or never-simultaneous sides) |
| 6 | paper_selected_starts | **5,399** | 1,244 | >=1 registered paper bet (H3-raw p_win > break_even + 0.02) |

Tier split at stage 3: Tier A (envelope commence, verified clock) 4,624 /
Tier B (clock proxy) 2,189.

## Contract-level ledger

| # | Stage | Rows | Excluded here | Rule |
| -- | --- | ---: | ---: | --- |
| 0 | k_market_quote_rows | 2,440,774 | — | pitcher_strikeouts + _alternate, regular season |
| 1 | price_valid_rows | 2,440,764 | 10 | \|price\| outside [1, 100000] (vendor junk) |
| 2 | paired_actionable_book_lines | 59,636 | — | per (start, line, book): one pair at the latest both-sides actionable clock |
| 3 | eval_observations (start, line) | 20,004 | — | ONE pair per (start, line): max total decimal, then BOOK_PRIORITY, then latest ts |
| 4 | contract_side_rows | 40,008 | — | over + under rows per eval observation |
| 5 | paper_bets | 11,435 | — | one per (start, line, side) where H3 edge qualifies; complementary sides NOT independent |

## Coverage after exclusions (recalculated; matches prep_summary)

| Tier | Eligible | Actionable quote | Closing ref | Both |
| --- | ---: | ---: | ---: | ---: |
| A verified clock | 4,624 | 4,514 (97.6%) | 4,622 | 4,514 |
| B clock proxy | 2,189 | 2,133 (97.4%) | 2,185 | 2,131 |
| **All** | **6,813** | **6,647 (97.6%)** | **6,807 (99.9%)** | **6,645** |

## Effective counts (PIN disclosure)

| Count | Value |
| --- | ---: |
| contract_side_rows | 40,008 |
| distinct (start, line) pairs | 20,004 |
| distinct starts | 6,643 |
| distinct slate dates | 270 |
| both-sides share of (start, line) pairs | 100% (pairing rule) |

Reconciliation: 7,194 = 62 + 294 + 25 + 166 + 4 + 1,244 + 5,399. Exact.
