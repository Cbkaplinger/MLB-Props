# LightGBM-to-count bridge - CORRECTED contract (2026-10-09)

> Status: DRAFT — NOT scored. Supersedes the showdown section of the
> 2026-10-08 audit packet (three corrections incorporated per owner).
> No commit/push/scoring in this turn.

## 0. Corrections to the 2026-10-08 audit packet

1. **Poisson is a valid distributional assumption.** `xK as Poisson
   mean` (count_layer.py:90-92) is a legitimate count model, NOT
   inherently a point-treated-as-distribution defect. The real
   limitations: (a) it does not integrate workload uncertainty (the
   mean of TBF is used, not its distribution); (b) independently
   calibrated per-line probabilities (WS1c) need not correspond to
   any single coherent PMF. This bridge replaces the whole count
   layer with the I3b mixture, which DOES integrate workload
   uncertainty.
2. **Under = 1 - over is CORRECT for half-lines** (odds_board.py:
   378-382; market.py:303-306 "no push on .5 lines"). Withdrawn as a
   defect. Integer-line pushes remain unhandled in the model path —
   an operational limitation only (first showdown stays half-lines).
3. **Denominator reconciliation EXECUTED (row-level, 2023, all
   pitcher-games, n=20,628):** production-style PA (NON_PA filtered
   BEFORE terminal-row selection, `plate_appearances()`,
   statcast.py) vs research-style PA (terminal row FIRST, then
   NON_PA filter, `bf_table_canonical`, run_corrected_history_2023
   .py:161-182): **K numerator agreement 100.000%** (20,628/20,628);
   **PA agreement 98.686%** (20,357) — all 271 mismatches are
   production = research + 1 (one +2), mean |diff| 1.004: exactly the
   predicted mechanism (ABs whose final pitch-row event is
   baserunning-only are kept by production via the earlier eligible
   row and dropped entirely by research). Both use the same
   NON_PA_EVENTS and STRIKEOUT_EVENTS vocabularies. Impact: the
   LightGBM target denominator differs from I3b N by at most ~1 PA on
   1.31% of pitcher-games; documented, not repaired. (verified from
   code + reconciliation run 2026-10-09)

## 1. Verified artifact inventory (recovered 2026-10-09)

Copied from the parked tree `MLB-Props\artifacts\models\` into the
worktree's gitignored `artifacts\models\` — the two REQUIRED bridge
artifacts only. Source/destination SHA-256 matched on every file
(transfer integrity). No pre-existing recorded hash was found for
these stems in tracked manifests, so these hashes are the NEW
reference record (transfer integrity proven; historical identity
rests on the sidecar self-description + Aug-21 selection CSVs).

| File | Bytes | SHA-256 |
| --- | --- | --- |
| lightgbm_krate_mono_20260821_054127.txt | 385,209 | `88b4ccd78e2ad8c45093474c50a9f38dbfd9f9da14c0995cab39ae41176ff12c` |
| lightgbm_krate_mono_20260821_054127.json | 3,306 | `e73af0364496557ca9e91fcd53694b92b9b53dabfd88a4463de85915d9cb69b4` |
| lightgbm_krate_20260821_054126.txt | 639,344 | `3e408ffcd6c9cb34be9b2a3ad98f8e1fbed0c611a959a6a99685f3896774f6ea` |
| lightgbm_krate_20260821_054126.json | 3,170 | `513c25529a9f0375de0cb04cdc368a6a8a1d8cf98d9a95540f82e1b84544d6b1` |

Verification (verified-from-artifact, this turn):
- Sidecar `features`: mono = 72 (`production_sparse72_monotone`),
  054126 = 58 (`production_final58_consensus`).
- Booster internal names are positional placeholders (`Column_i`);
  counts match sidecars exactly (72/72, 58/58). The live loader binds
  positionally in sidecar order (`lightgbm_matrix` + live_assembly.py
  :91-110), so the sidecar list IS the frozen feature contract.
  Feature-safety conclusions remain PROVISIONAL until the full 72/58
  lists are audited against the leakage rules (done for the registry
  definitions; full sidecar-by-sidecar check is a pre-showdown step).
- Both sidecars: `sample_weight: none`, train 6,557 rows through
  **2024-06-08**, validation 2024-06-09..08-05 (n=1,404), test
  2024-08-06.. (n=1,413), train_seasons [2023, 2024].
- Sidecar records training-artifact sha `eb6e923b...` for
  `pitcher_training.parquet`; the current file hashes `dfddfff8...`
  (75,582,165 B) — **the exact training frame is no longer on disk**;
  historical training-data identity is NOT verifiable. The boosters
  themselves are byte-verified frozen.
- Zero-weight member (`054152`, weight 0.0) NOT copied: the live
  loader would still load it if present, but it contributes 0 to the
  blend; documented loader behavior, no production change. OPTIONAL
  (pricing-chain only, not copied): `tbf_pa_ridge_..._20260728.joblib`,
  `prob_calibration_ws1c_platt_20260910_012559`, pointer JSONs — all
  present in the parked tree for later pricing-chain reproduction.

## 2. Prediction-provenance table

| Prediction set | Feature set / lineage | Rows, dates | Out-of-training-sample? | Usable for the showdown? |
| --- | --- | --- | --- | --- |
| `model_quality\phase11b_walkforward\walkforward_predictions.parquet` | 180-feature step10 set, estimator defaults, compare_freeze `20260728_033241` — NOT the active ensemble | 4,607 rows, 2024-04-01..09-30, 3 WF windows, per-row `k_rate_pred`/`projected_tbf`/`expected_K`/per-line probs | YES — genuinely chronological (train strictly before each window) | NO for promotion: lineage does not match the active ensemble members |
| `phase11b_walkforward_production*` variants (sparse40, stable12, +discipline, +xwoba_luck, research_*) | per-dir metadata; none is sparse72/mono/final58 | same 3 windows | YES per window | NO — wrong feature sets |
| `sparse72_model_family_ablation/.../outer_results.csv` | sparse72 + sparse72_monotone, folds outer_2024_h1/h2 — aggregates only, no per-row predictions | 2,244-2,467 test rows/fold | fold-level OOF | metrics context only |
| Frozen boosters scored on rows after their train_end (2024-06-08); validation 06-09..08-05 used for early stopping; TEST window 08-06+ never used for stopping | THE active ensemble members (byte-verified) | eval 2024-08-06..10-01 ≈ n~1,400 booster-test + I3b Sep window | out-of-TRAINING but selection-aware: the Aug-21 ensemble sweep (`ensemble_sweep_...aug21_deduped`, generated 2026-08-21, 5,544 rows, market-ROI objective) inspected outcomes through ~Aug 21, 2026 — including 2025 and post-freeze-2026 rows for WEIGHT selection | YES as the primary predictive comparison, labeled "frozen model scored after its training cutoff, selection-aware" (owner table row 3) |
| Mechanical smoke test | same, on training-period rows | — | no | no promotion claim |

**2025/2026 outcome awareness (documented usage):** config gates 2025
out of fitting (`config.py:53-56`, `load_frame` season filter); 2025
used for discipline-lift confirm + policy selection (contaminated,
disclosed); the Aug-21 ensemble sweep scored market outcomes through
its 2026-08-21 generation date → post-2026-08-03 is NOT untouched;
the only forward-clean block is after the bridge contract date.

## 3. Corrected showdown contract (frozen design; NOT executed)

**Scientific question:** does the frozen ensemble's rate output
produce better K distributions than log5 when both use identical I3b
workload distributions?

### Arms

- REF: canonical I3b BF PMF + canonical log5 p* + kcount combiner
  (unchanged).
- CHAL: identical BF PMF + identical combiner + identical rows;
  ONLY p* replaced by the frozen ensemble's blended k-rate
  (0.6*mono + 0.4*final58, existing [0,1] clip only). No new
  calibration; rate-calibration checks are DIAGNOSTICS only.

### Evaluation layers (separated)

1. **Mechanical smoke test** (no promotion claim): frozen boosters
   scored on 2023 rows (their own training rows) + pipeline identity
   checks (feature-matrix column order == sidecar list; output in
   [0,1]; no NaN). Pass/fail only.
2. **Predictive evaluation (primary):** the 2024 post-training-cutoff
   window `2024-08-06..2024-10-01` intersected with the I3b
   September-origin eval rows (n ≈ 770) PLUS the validation window
   2024-06-09..08-05 as a disclosed selection-aware secondary.
   2023 rows = smoke-test only (in-sample for both boosters).
   **No defensible active-set OOF exists** (verified: no WF parquet
   for sparse72/mono/final58; nearest OOF is the 180-set July-28
   lineage) — reported BLOCKED for OOF-based comparison; one
   concrete next proposal: run the EXISTING walkforward_stack_backtest
   machinery (no new tuning) for the two active feature sets to
   generate matching-OOF predictions, requiring separate
   authorization.
3. **Prospective confirmation:** 2026 post-contract rows, later.

### Population, matching, coverage

- Rows: I3b 2024 eval rows (both starters) matched 1:1 on
  (game_pk, pitcher) to LightGBM-scorable rows. **Never exclude
  primary rows using eventual PA>=9**; PA>=9 only as an explicitly
  outcome-conditioned sensitivity. Debut/sparse rows stay eligible
  (feature availability is outcome-independent; NaN-tolerant models).
- Coverage accounting: every unmatched row reported with reason
  (missing starter identity, missing feature column, lineup join
  failure); matched-coverage rate frozen >= 95% of I3b rows or
  BLOCKED.
- Reconciliation gate: per-row K and PA agreement between the
  production label builder and the research target on the matched
  population (K 100% required; PA mismatches reported with the
  documented +1 mechanism; systematic disagreement > 2% of rows =
  BLOCKED).
- Feature-invariance test: for a sample of matched rows, recompute
  feature vectors under two artificial current-game outcomes and
  assert identical values (contract requirement; catches same-game
  leakage mechanically).

### Numerical safety tolerances (replacing "no safety regression")

- Count-PMF mass: |sum-1| <= 1e-9 both arms; no negative entries.
- Probability floors: identical (1e-12 clip) both arms.
- xK: |xK_CHAL - xK_REF| reported per row; pooled |mean bias| delta
  <= 0.05; MAE delta <= 0.02.
- Count-RPS safety (CORRECTED 2026-10-09, before the canonical run's
  final evaluation): the challenger must not be confidently worse
  than the degradation floor — FAIL only if the paired full-window
  CI's LOWER bound exceeds +0.0005 (i.e., ci_lo95 > +0.0005). The
  originally drafted wording ("CI lower bound >= -0.0005") was a
  spec error: it would fail ANY improvement larger than the floor.
  Two interim implementations compared the wrong CI side; the final
  rule above is the intended degradation check. Disclosed; no owner
  gate affected (owner gates = denominator + feature gates).
- Floor rows: challenger <= reference + 0.
- PIT tail bins <= 1.5x expected both arms (Sept + full window).
- Bootstrap: slate dates, 2,000, seed 20261001.
- Reference reproduction tolerance: 1e-6 (cross-process float drift
  in the sklearn refit measured at 5.3e-8/8.4e-8; mechanical identity
  assert, ~4 orders below decision relevance; disclosed).

### Metrics and gate

Primary: paired count-RPS (CHAL-REF) on the predictive window, CI
entirely below 0 = pass. Secondaries: log score, xK bias/MAE,
milestone Brier + ge10/ge12 reliability (ABSOLUTE changes reported),
PIT, per-origin + permanent slices (career debut, season debut,
sparse, returning, short outing N<9, April, September, ge12).
Lineup-representation difference (card slots vs opp_lineup
aggregates) disclosed as an inseparable component of the rate input.
Decision: promote only on primary pass with ALL numerical-safety
tolerances met; otherwise keep log5 p* and close the raw-rate bridge.

## 4. Readiness verdict

**READY WITH BLOCKERS** for the frozen-model post-cutoff predictive
comparison; **BLOCKED** for an OOF-lineage comparison with the active
ensemble (no matching OOF artifact exists; generating one requires a
separate authorization to run the existing WF backtest for the two
active feature sets — no retraining of the frozen boosters
themselves).

Ranked blockers:
1. (comparability) No OOF predictions with active-ensemble lineage —
   resolved by choosing the post-cutoff design (recommended) or
   authorizing the WF run.
2. (correctness, resolved) artifacts recovered + hash-verified;
   booster/sidecar feature binding verified positional.
3. (correctness, documented) production-vs-research PA differs on
   1.31% of rows (+1, baserunning-terminal ABs); frozen reconciliation
   gate added to the contract.
4. (leakage, provisional) feature-safety verified from registries +
   validators; full 72/58 sidecar lists not yet line-by-line audited
   against leakage rules (pre-showdown step).
5. (operational) historical LightGBM scoring needs the live feature
   builder run on historical slates (announced lineups unavailable →
   proxy inputs; train-serve skew disclosed).
