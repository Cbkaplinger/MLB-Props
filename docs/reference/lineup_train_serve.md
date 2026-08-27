# Lineup membership: training proxy vs live announced order

**Status:** documented decision (not a feature reopen)  
**Date:** 2026-07-28

> Metric lane note: this document explains a data-contract issue, not winner
> selection. Use `docs/reference/governance_metric_stack.md` for current
> champion metrics/lane outcomes.

## Short answer

**No — “first nine by first PA” is not the same as the announced batting order.**

| Setting | What we use | When it is known |
|---|---|---|
| **Training / Level 3 history** | First nine *distinct batters who actually appeared*, ordered by their **first plate appearance** in that game (`is_initial_lineup`) | **After** the game (reconstructed from Statcast) |
| **Live / daily projections** | RotoGrinders **announced** batting order (projected or confirmed) | **Before** first pitch |

They usually overlap a lot for conventional starts. They are not identical.

## Why the historical proxy exists

Statcast does not ship a clean “announced lineup at lock” field for every historical game. For research rows we therefore approximate the starting nine from who actually hit, in appearance order. That:

- drops pure pinch-hit / late defensive replacements who never started;
- still **can differ** from the carded lineup when there are late scratches, EH/DH quirks, double-switch chaos, or a batter who was announced but never got a PA before an early hook.

So the ablation that says “opponent lineup matters” is evidence about **this proxy’s aggregates** in training, plus **announced-order aggregates** at score time. That is a **train/serve skew**, not a bug in the live path.

## What “fixing” this would mean

Not “use top 9 of the lineup” — live already does that via RG. The open work is:

1. Keep documenting the skew (this file).
2. When enough `(logged announced lineup, postgame first-9)` pairs exist, **measure overlap** (Jaccard / slot agreement) and whether ΔMAE from lineup ablation still shows up under announced-only features.
3. Do **not** reopen frozen sparse-set production features from announced history
   until a nested chrono screen exists with historical announced lineups (we do
   not have a multi-year announced archive yet).

## Ops reminder

- Live: `Python.daily_lineups` → `live_assembly` opponent means from **announced** IDs.
- History: Level 3 joins batters with `is_initial_lineup` from Level 1.
- Projection log should record `lineup_source` / note (see `production/projections/log_projections.py`).

## Roster ID resolve (live)

Scraped RotoGrinders names are matched only within the **same team's** official
MLB Stats API roster, widening in order until every card resolves (or the run
fails):

1. **`active`** — current active roster  
2. **`40Man`** — 40-man (covers some IL / option cases still on cards)  
3. **`fullSeason`** — season roster (covers rare call-ups still listed on RG)

Model joins continue to use numeric MLB person IDs only.
