# Transfer-validation readiness - DRAFT (2026-10-08)

> Status: DRAFT. No 2024+ outcomes read; no validation run. This is
> the inventory the owner requested before authorizing ONE transfer
> evaluation. Produced by the reusable evaluation package work (B).

## 1. Seasons already inspected (NOT pristine holdouts)

| Season | Status | Notes |
| --- | --- | --- |
| 2022 | inspected | prior-season inputs only in the overhaul; 2023 runners consume it via history/fallback; BF/PA behavior partially audited |
| 2023 | **heavily inspected** | all overhaul experiments score it; every gate, residual, and tail analysis above is 2023; NOTHING here can be reused as validation evidence |
| 2024 | outcomes never read by overhaul research | a 2024 Savant parquet exists on disk (sha on record in the handoff); its outcomes are UNREAD by the count lane; 2025/2026 paper lanes used 2025-2026 odds/outcomes but the overhaul never touched them |
| 2025/2026 | production/paper lanes only | locked retrospective; no-2026-tuning rule stands |

**Rule:** no previously inspected season may be labeled a pristine
holdout. 2024 is the nearest-to-clean candidate but must be treated
as "outcome-unread by this research line," not untouched by the owner.

## 2. Available historical input contracts

- Savant 2022/2023 regular-season parquets: approved + SHA256-verified
  (2023 `b9f9db99...`, 2022 `63d40a49...`) - `default_sources`.
- 2024 Savant parquet: on disk, hash on record; acquisition contract
  mirrors 2022/2023 (same schema, verify_and_load).
- Retrosheet 2022/2023 event archives + Chadwick register (I4 lane):
  acquired, hashed, gitignored.
- Missing: 2024 Retrosheet archive (needed only if the I4 mapping
  enters validation), verified pregame starter/lineup capture
  (BLOCKED - see 3).

## 3. Known starter/lineup availability limitations

- All overhaul forecasts use the PROXY previous-game card (I3b) and
  pregame-reconstructed starting pitchers - not verified pregame
  announcements. Transfer validation therefore measures the model
  chain, not a deployable pregame forecast.
- Announced-lineup/starter capture is a separate acquisition lane
  (historical pregame snapshots) - not acquired; BLOCKED without
  authorization + a vendor decision.
- Injuries/late scratches: unreconstructed in history; documented as
  a known limitation of the BF lane.

## 4. Independent BF reconciliation requirement (pre-validation gate)

The BF target itself (batters faced from Savant PA counts) has never
been reconciled against an independent source (Retrosheet event data
or box scores). Before any transfer claim: run the I4-style
Retrosheet mapping on the validation season and confirm BF/PA row
agreement (report agreement rate + mismatches). This is read-only
diagnostics, not modeling.

## 5. Proposed locked recipe for transfer (the candidate)

- BF workload: expanding-history hazard model (arm B, frozen 2026-10-07
  manifest `workload-training-policy-20261007_090000`), overflow
  handling per its frozen extension (I5 tail recipe CLOSED - failed
  its gate + worsened ge12).
- PA strikeout: shrunk log5 p0 (frozen richer spec rejected).
- Opponent rate: I3b previous-game card-informed p* (recorded
  developmental benchmark).
- Count distribution: I3b homogeneous-p* mixture via I3b saved PMFs.
- Refit schedule: NONE within the validation season (strictly
  expanding only as the frozen runner already does - no mid-season
  retuning); all parameters fixed at 2023 values.
- Metrics: count-RPS (primary), BF-RPS, signed mean bias (BF and K),
  milestone Brier + ge10/ge12 reliability, log-score floor counts,
  variance-accounting ratio, seeded discrete PIT - all via
  `eval_package.py` (IMPLEMENTED).
- Decisions: PASS = CI-defined improvement vs the frozen 2023
  benchmark recomputed on the validation season AND ge12 reliability
  not worse than the benchmark's; FAIL = any primary CI loss or
  material tail deterioration (record, keep benchmark).

## 6. Acceptable calibration / tail criteria (pre-registered)

1. Count-RPS paired CI vs benchmark: no CI-detectable degradation.
2. ge12 absolute reliability: not worse than benchmark's by >0.005
   (2023 benchmark value -0.0008).
3. Mean-BF bias (pred-act): within +/-0.35 pooled (2023 pooled was
   +0.27; I5's failed correction showed the band matters).
4. PIT: no bin with >1.5x expected count in either tail bin.
5. Sparse cells (events < 5): reported, never used for pass/fail.

## 7. PROPOSED validation authorization (ONE, owner-gated)

```text
# Transfer Validation - 2024 Season (DRAFT, requires owner decision)
1. Acquisition: verify + hash the existing 2024 Savant parquet;
   acquire 2024 Retrosheet archive + reuse the Chadwick register
   (BF reconciliation only).
2. Gate 0 (BF reconciliation): Retrosheet vs Savant BF/PA agreement
   >= 99% of rows; investigate mismatches before scoring.
3. Scored validation run: frozen 2023 recipe, 2024 outcomes, origins
   at 2024-04-15/07-01/08-01/09-01, strictly expanding training
   (2022+2023+2024-to-origin), eval_package metrics + frozen criteria
   (section 6). ONE run; preserve all attempts.
4. Report: I5-style manifest + eval package report; PASS/FAIL per
   section 6; no tuning, no recipe modification, no production.
5. Prohibited: 2025/2026 outcome reads; announced-lineup acquisition;
   any production-path change.
```
