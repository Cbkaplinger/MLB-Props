# Juiced frozen-model replay ledger — 2026-09-11

> Point-in-time measurement. Not a work queue. Standing spec:
> [`../oddsapi_replay_architecture.md`](../oddsapi_replay_architecture.md).
> Script: `production/ops/market_research/juiced_replay_ledger.py`.
> JSON: `artifacts/odds_log/juiced_replay_report.json`.
> Next actions: `docs/EXECUTION_BACKLOG.md`. **Do not retune live floors,
> veto, or Kelly from this run.** 2026 is confirmatory (prior harness peek).

**Question:** at juiced two-way prices, with live policy as a filter only
and rejected candidates retained, does frozen `p_ours_cal` print a
positive flat-1u paper edge on 2025+2026 open/morning?

**Answer:** yes on paper, fills unmodeled. Canonical universe (owner
2026-09-11) is **DK else FD else next US book** — n=2,077, ROI **+7.3%**,
WR 0.506, CLV +1.08pp. DK+FD-only is a sensitivity (n=982, +12.3%,
WR 0.580), not the headline. 2025 (selection year) is +4.2%. 2026
(+12.6%) must not drive a live change.

## 1. Contract

| Piece | Setting |
| --- | --- |
| Model | Frozen `p_ours_cal` from `universe_panel_live` (Poisson + WS1c) |
| Edge | Two-way multiplicative de-vig at the juiced book pair (same as live `evaluate_side`) |
| Decision clock | Friend OPEN if both sides exist, else paid MORNING. Never close as an input. |
| Book pick | DK else FD else next US book with a two-way quote (**canonical**) |
| DK+FD-only | Sensitivity arm. Owner kept next-book for coverage. |
| Policy filter | Live line floors + 4.5-over veto + 2.5/3.5 probation bump 0.18 |
| Sizing | Shadow only: flat 1u / edge-band / 1/16-Kelly / robust Kelly |
| Close CLV | Dropped when vendor timestamp is after commence (12 events flagged) |
| Fills | Unmodeled |

GO said DK→FD→median. Script implemented next-book because a median is
not a fillable ticket. Owner 2026-09-11 locked next-book as canonical
and kept DK+FD as the labeled sensitivity.

## 2. Headline (flat $50 unit)

| Slice | n | ROI | WR | CLV pp | open share |
| --- | ---: | ---: | ---: | ---: | ---: |
| All-books (canonical) | 2077 | +7.3% | 0.506 | +1.08 | 0.495 |
| DK+FD-only (sensitivity) | 982 | +12.3% | 0.580 | +1.37 | 0.801 |
| 2025 (selection year) | 1308 | +4.2% | 0.487 | +0.95 | 0.537 |
| 2026 (confirmatory) | 769 | +12.6% | 0.540 | +1.30 | 0.424 |
| 1/16-Kelly (all books) | 2077 | +6.6% | 0.506 | +1.08 | 0.495 |
| Edge-band | 2077 | +6.4% | 0.506 | +1.08 | 0.495 |
| Robust Kelly | 1811 | +7.8% | 0.472 | +1.11 | — |

Sizing did **not** beat flat on ROI. Robust n drops 266 tickets to
Kelly-zero after the 50% shrink toward 0.5.

Rejects: below_floor 12,542 / no_two_way 3,128 / veto_4_5_over 1,866 /
taken 2,077. Over-share on taken = 0.21 (veto working). Close-invalid
CLV drops left n_clv = 2,075 of 2,077.

## 3. Book mix (why all-books ≠ DK+FD)

Next-book fallback soaks BetRivers when DK/FD lack a two-way at the
decision clock (mostly morning: BetRivers open-share 0.20 vs DK 0.79).

| Book | n | ROI | WR | CLV pp | open share |
| --- | ---: | ---: | ---: | ---: | ---: |
| BetRivers | 1001 | +2.3% | 0.429 | +0.84 | 0.197 |
| DraftKings | 847 | +12.0% | 0.580 | +1.33 | 0.793 |
| FanDuel | 135 | +14.4% | 0.585 | +1.64 | 0.852 |
| BetMGM | 55 | +9.8% | 0.582 | +0.67 | 0.291 |
| Fanatics | 32 | +4.6% | 0.531 | +0.12 | 0.844 |
| BetOnline | 5 | −2.4% | 0.600 | +1.89 | 0.200 |
| Bovada | 2 | +15.0% | 0.500 | +0.74 | 0.500 |

BetRivers was already a QA flag (alt-line bleed vs ~8k props/book). It
is 48% of canonical volume and most of the WR drag. Keeping it in the
headline is a coverage choice, not a claim that BetRivers is a good
fill.

## 4. Probation 2.5 / 3.5 (data, not a live change)

Skip-all 2.5/3.5-over: n=1,999, ROI +7.41% vs live +7.28% — noise.

| Cell | n taken | ROI | WR | Note |
| --- | ---: | ---: | ---: | --- |
| 2.5-over | 18 | −4.9% | 0.50 | Thin, red. Keep hard floor. |
| 3.5-over | 60 | +6.5% | 0.517 | 2025 −10% (n=46) vs 2026 +61% (n=14). Do not skip-all. |
| 3.5-under | 42 | −8.2% | 0.310 | Thin, red. Revisit at October nested judge. |
| 2.5-under | 0 | — | — | Floor already starves it. |

Half-size sits between live and skip-all. **Do not half-size live. Do
not skip-all. Freeze current probation floors.**

## 5. What this does *not* authorize

- Retuning live floors / 4.5-over veto / 1/16-Kelly from 2026 +12.6%.
  That is the nested-hole again (#109 / SOP §8). 2025 +4.2% is the
  honest selection-year number on the canonical (softer) book mix.
- Promoting DK+FD +12.3% as money-truth. Fills unmodeled; owner kept
  next-book as canonical.
- Changing BET/HOLD. Offset cap and morning edge cap still wait.
  Stacker stage 2 is still shadow-only until a separate go.

## 6. Owner decisions recorded 2026-09-11 (after this ledger)

1. Canonical fill universe = next-US-book fallback (coverage over purity).
2. Next coding after polish = stop policy work on this ledger.
3. Featured `totals` pull GO (~7.3k credits, slate environment).
4. Live retune from this run = **refused**. Needs a named floor/veto
   change plus written acceptance of the 2026 peek. See Snapshot.

Featured totals live in `pull_featured_totals.py` (calendar clocks:
morning 12:00 ET, evening 19:55 ET — not first-pitch). Lake on disk:
`data/Odds-Historical/theoddsapi/featured_totals.parquet` (220,482 rows /
4,749 events / 363 days, ~7.3k credits, remaining 3,714,815). Join later
for slate-cap research; they are not a K feature.
