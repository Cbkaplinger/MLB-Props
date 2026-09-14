# Ratings, hook table, wake auto-run — 2026-09-14 (dated evidence + method)

> Point-in-time. Live plan: `docs/EXECUTION_BACKLOG.md`. Generators:
> `production/ops/market_research/glicko_pitcher_ratings.py`,
> `production/ops/market_research/hook_pull_table.py`,
> `production/ops/run_wake_recovery.ps1`. Nothing here touches live policy.

## 1. Glicko-style ratings — methodology

For each starter, chronological walk over L3 (2023→now):

- **Rating R** = `(prior_PA * league_Krate + sum(K)) / (prior_PA + sum(PA))`,
  prior_PA = 300 (~one season of league-average pseudo-PA). Debutants start
  at league average; every start pulls R toward the pitcher's own rate.
- **Uncertainty RD** = `max(floor, sqrt(league) / sqrt(prior_PA + PA_seen))`,
  floor 0.004, debut 0.030. More PA → narrower RD. Between starts RD grows
  `+0.00004/day` (layoff decay — long layoffs re-widen uncertainty).
- Result: 601 pitchers, league K-rate 0.219. **YoY r = 0.938 (n=427)** —
  clears the SOP 0.7 stability gate by a mile.

Top (Misiorowski .327, Crochet .306, Glasnow .304, Snell .303, Skubal .302)
and bottom (Vasquez .155 … Senzatela .150) both pass the smell test.
386 arms carry wide RD (≥0.015) — the young/declining staleness tails,
now quantified per pitcher instead of per cohort.

## 2. Where Glicko slots into the pipeline (and where it lives now)

```
L3 starts → glicko ratings table (R + RD per pitcher, rebuilt with L3)
   → (a) retrain FEATURE: R as slow prior + RD-gated shrinkage of k-rate
   → (b) overlay: shade xK toward league avg proportional to RD
   → Poisson + WS1c → policy (unchanged)
```

Today it lives at step 0 only: standalone table
(`artifacts/odds_log/glicko_ratings_current.parquet`). Path (a) needs a
retrain window (offseason); path (b) needs a ledger-gate like kadj had
(kadj died there — same gate applies, no promises). No minors data needed:
Glicko runs on MLB results; minors only matter for call-up priors (parked WS2).

## 3. Hook table — what "base pull 10%" means and how TBF uses it

Of 353,824 starter PAs (2025–26 Savant), the starter is pulled after exactly
**10.0%** — i.e., one PA in ten ends a start. The average hides the shape:
90–99 pitches + 3rd time through ≈ 32–37% pull; early/low-count ≈ 2–5%.
103 cells, 54 thin (n<200, flagged, never cited).

Uses, in order of honesty:

1. **Monte Carlo pull decision** (post-season): at each simulated batter,
   look up P(pull | pitches, TTO, score, inning). This table IS that lookup.
   Missing before it: bullpen-rest + pitcher random effects.
2. **TBF distribution, not point**: today's ridge predicts one TBF number
   (MAE ≈ 2.5, hooks +9.5 / marathons −5.4). The table says TBF is a
   distribution with a 10%-per-PA hazard — marathon error is irreducible
   pregame (in-game score/manager unknowable), so the fix is policy-side
   (discount marathon-dependent exposure) + fat tails, per WS3v3.
3. **Target metrics if anyone re-attacks point TBF**: MAE_TBF overall AND
   tail MAE (hooks PA<18, marathons PA≥28) AND downstream universe Brier —
   all three, same-subset, chrono-gated. WS3 killed three variants on
   exactly these; a challenger must beat all three, not just overall MAE.

## 4. Wake auto-run — status

`run_wake_recovery.ps1` exists and parses. `setup_automation_tasks.ps1` now
registers `MLBProps_WakeRecovery` at logon +5min — **staged, not live**:
ONLOGON registration needs an elevated shell, so it activates on your next
elevated setup run (batch with NightlyDrift registration). Deliberately
unwatched by self-check (a never-run logon task has no Last Result and
would page RISK — the task IS the recovery). Direct registration from this
session failed with Access denied (documented, not retried).

## 5. Sustainability / revert map (session work)

| Piece | Revert (one line) | Why safe |
|---|---|---|
| `kpi_policy` bankroll block | delete the key | Nothing in prod code reads it (verified by grep) — declaration only; enforcement is existing exposure_controls |
| Exposure columns | delete `_attach_slate_exposure` call + helper | Comment says so; 2 tests pin columns-only behavior |
| Banner `$_` (4 scripts) | git revert | Old text was provably blank; new text proven non-blank |
| Wake task (when registered) | `schtasks /Delete /TN MLBProps_WakeRecovery /F` | Outside repo; self-check ignores it |
| Glicko / hook / audit scripts | delete files | Standalone; zero prod imports |

## 6. Where we are going (no new builds without a named order)

Rest of season: boards log under the champion; settle post-game; closeout
cadence. Owner minutes: elevated setup run (NightlyDrift + WakeRecovery),
dawn probe, fills. October: slate caps → full-season judge → stacker
verdict → cloud. Stop-out stays verbal (owner rejected −20u).
