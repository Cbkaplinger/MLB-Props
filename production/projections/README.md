# production/projections — projection slate lifecycle

## Purpose

Turn features into the daily projection slate the board scores, then grade
those projections against actuals. Projections are the frozen-probability
input; quotes are somebody else's problem (see `../odds/`).

## Flow

1. `log_projections.py [--allow-stale]` — scores the frozen bundle over
   today's starters (Statcast/L3 features + RotoGrinders lineups), appends
   to `artifacts/projection_log/projections.parquet`. Re-logs on every
   board run (dynamic lineups); `--allow-stale` labels lag instead of
   aborting (the 2026-09-04 zero-bet lesson).
2. `grade_projections.py --all-logged` — joins actual Ks, writes MAE_K and
   per-date grades (feeds model-health monitors, never the trainer).

## Rules

- Projections never see odds or closes (market never enters the trainer).
- Labels ride along as labels only (leakage-safe by construction).
- A missing slate is a documented gap, never backfilled by rescoring
  (fabricated paper is worse than missing paper).
