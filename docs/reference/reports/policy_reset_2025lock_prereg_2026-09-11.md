# Policy reset pre-registration — 2025-lock (owner-directed 2026-09-11)

> Standing spec: `../oddsapi_replay_architecture.md` §5.5. Next actions:
> `docs/EXECUTION_BACKLOG.md`. 2026 is a **disclosed-peek** judge
> (blindness broken by #93 + juiced slice + this doc's numbers) — labeled
> everywhere, never presented as clean.

## Selection set (2025 juiced only)

`juiced_replay_candidates.parquet` rows with `yr == 2025`, decision clock
friend-open-else-paid-morning, juiced DK→FD→next-US-book prices, frozen
`p_ours_cal`. Rejects kept. Fills unmodeled.

## Locked candidate family (pre-registered, no additions after seeing 2026)

- Floors: {0.08, 0.10, 0.12} translated to juiced (fair minus ~3.3pp).
- Cap: {0.18, 0.20, 0.24} (edge_cap HOLD reason).
- Robust refusal: {off, on}. Measured 2026-09-11 on the full lake: cap-only
  2025 +8.0% (n=912, WR 0.53) vs base +4.2%; refusal-only 2025 **-0.2%**
  (n=618, WR 0.35) — refusal concentrates into plus-price longshots and
  starves DK+FD (982→16 combined). Refusal stays OFF live; re-tested here
  as a dimension, not a default.
- Side rules: {both sides, under-lean}.
- Veto 4.5-over: {on} (not searched — standing risk control).
- Probation 2.5/3.5-over bump 0.18: {on}.
- Book universe: next-US-book canonical + DK+FD-only sensitivity.
- Grouping dimension (owner 2026-09-11): consensus morning line per player
  O/U (devigged median) hung beside `p_ours_cal` on the same line×side cell.

## Selection rule (run once, on 2025 only)

Champion = max lower-confidence-bound LCB_95(ROI) on slate-clustered
block bootstrap, subject to: CLV ≥ 0 after vig, no single line×side cell
more than 40% of PnL, top-book robustness (DK+FD-only ROI same sign).
Not max ROI. Engine work needed: `--floors/--cap/--side-rule` overrides
in `juiced_replay_ledger.py` (today it reads live policy only).

## Judge (2026, once, disclosed peek)

Score the single champion on 2026 rows once. Report same constraints.
A pass does not auto-promote — promotion is a separate sign-off with the
peek disclosed in the commit message.

## Exception already enforced (named live change, same day)

Morning `edge_cap = 0.20` went live 2026-09-11 per explicit owner order,
ahead of this judge, with the peek accepted in writing (backlog OWNER
DECISIONS). `robust_refusal` shipped with it and was **reverted the same
day** after lake measurement showed it destroys the selection year. Full
suite 336 green; pin updated same commit.

## Promotion (executed 2026-09-11, owner order)

Champion promoted the same day it was judged: cap 0.20 → 0.24,
`under_lean_premium` 0.04, `fill_books` [DK, FD]. Board-fired that evening
(Snell U7.5 FD BET at 19.3% — under the 0.24 cap that refused it at 0.20
that morning). Stakes/veto/probation/clip/Kelly untouched. 345 green.
Peek disclosure in backlog PROMOTION bullet.
