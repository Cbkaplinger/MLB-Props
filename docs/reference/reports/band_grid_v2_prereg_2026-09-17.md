# Band-grid v2 preregistration (locked 2026-09-17, owner order: Execute)

Supersedes the "same 36-family PLUS no-cap" October plan (backlog 2026-09-17):
family-v2 below is a strict superset of it. This document is the contract; the
executor is `production/ops/market_research/band_grid_v2.py`.

## Why a new family

The 36-family assumed caps help (all caps ≤ 0.24) and never contained the
no-cap rule. On 2026 the refused set earned +11.5% — the assumption failed
out-of-sample. v2 searches floors, caps (including none), side handling,
books, and line-floor handling jointly, on data nobody has seen.

## Grid (80 configs)

| Dimension | Values |
|---|---|
| Floor | uniform {0.08, 0.10, 0.12, 0.14} + file-map (live `line_floor_policy.json`) = 5 options |
| Cap | {0.18, 0.20, 0.24, none} |
| Side | {both, lean (+0.04 over premium)} |
| Books | {next (all), dkfd} |

5 × 4 × 2 × 2 = 80. Contains all 36 old configs (uniform 0.08–0.12 ×
0.18–0.24 × both/lean × next/dkfd) plus no-cap arms, the 0.14 floor, and the
file-map variant. 4.5-over veto + 2.5/3.5 probation always on (file map embeds
its own levels: 2.5→0.20, 3.5→0.18). Unknown lines in file mode default 0.12.
Flat $50 economics via canonical `bet_pnl`. One row per prop already (book
pre-assigned at candidate build; verified 6,138 = 6,138).

## Selection slice (the blindness)

`gd >= 2026-09-28` (first slate after the September closeout), frozen
candidates only, no retraining, no re-devig. The executor **refuses** any
`--select-from` earlier than 2026-09-28 unless `--allow-peeked` is passed, and
`--allow-peeked` runs are labeled PEEKED and can never promote. Default runs
before the slice exists produce a valid empty selection (plumbing proof, no
peek — there is nothing to see).

## Selection rule (identical to 2025-lock, N=80)

1. min-n: config n ≥ 200 on the selection slice, else ineligible.
2. Constraints (all required): CLV mean ≥ 0; max line×side cell ≤ 40% of PnL;
   DK+FD-subset ROI same sign as config ROI (for books=next legs).
3. Pick max LCB_95(ROI), slate-clustered bootstrap, 2000 draws, seed 20260917.
4. White-lite over all 80 (demeaned best-of-80 luck): promotion requires
   p < 0.05 AND winning LCB > 0. Either fails → no promotion, live stays.

## What happens after

Single official execution post-closeout. Winner is promoted exactly (floors,
cap incl. none, lean, books, line-handling) with pin + board-fire, same
ceremony as 2026-09-11. Cell-exclusion + month-exclusion stress reported
alongside, advisory only. This prereg + the executor + its tests are the full
build; nothing here touches production, live policy, or the model.
