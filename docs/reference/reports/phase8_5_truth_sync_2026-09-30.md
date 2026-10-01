# Phase 8.5 Truth Synchronization -- Feature Lineage, Tree Verdict, MLflow Decision Inputs (2026-09-30)

Scope: last broad documentation pass for the model thread. Read-only investigation;
writes are this report, a PROPOSED ADR, and a CONTEXT.md status refresh. No
implementation, no skill invocation beyond documented reads. PA-thread artifacts
read as evidence; PA-thread files not modified.

## 1. Exact L3 (PA development baseline) feature list

Source of truth: `research/offseason_2026/experiments/logistic_pa/bundle/feature_manifest.json`
(24 columns declared; 21 active model inputs) + `logistic_pa/card.json` families.

| Family | Columns (exact) | Window / construction |
|---|---|---|
| F1 platoon (2) | `same_hand`, `b_hand_rate` | b_hand_rate = batter K-rate vs pitcher's handedness; season-to-date, 200-PA EB shrink toward league (0.223813) |
| F2 batter discipline (3) | `b_whiff`, `b_swstr`, `b_chase` | batter season-to-date shrunk rates (std) |
| F3 pitcher discipline (10) | `p_whiff_P5`, `p_swstr_P5`, `p_chase_P5`, `p_zone_P5`, `p_contact_P5`, `p_whiff_std`, `p_swstr_std`, `p_chase_std`, `p_zone_std`, `p_contact_std` | BOTH windows by pre-registration: P5 = last-5-starts rolling; std = season-to-date. "no per-window post-hoc selection" (card) |
| F4 history (2) | `log_pa_curr`, `log_pa_prior` | log1p of current-season and prior-season PA counts |
| F5 park (1) | `park_k` | prior-season EB park factor (500 PA prior), keyed (season, home_team) |
| F6 rest (2) | `rest`, `debut` | EXCLUDED from the next-PA-K manifest (Phase 7 2023-fold ablation ~zero); kept eligible for opportunity/TBF research |
| L3 interactions (4) | `trip_eq_2`, `trip_eq_3`, `trip_ge_4`, `spi_over_9` | per-PA-within-game: through-order trip dummies + starter_pa_index/9 linear |
| Baseline input (1) | `logit(P3)` | P3-log5 prior (M2 odds-form, pitcher EB x batter EB / league) as fixed-structure offset input |

Model: L2 ridge logistic (offset = logit(P0) with b estimated) + the 4 trip/index terms.
Imputation: nan_to_num(0) except `b_hand_rate`->league, `park_k`->1.0, `rest`->15.0.
Reproduction: L3 bundle reconstruction reproduces stored L3 predictions to 2.2e-16
(logistic_pa/bundle/; see also bundle/provenance_sidecar.md). [C2 correction 2026-09-30:
previously misattributed to the tree run.]

## 2. Did the tree inherit the old 58/72 feature sets?

**No.** Verified two ways:
1. `tree_pa/card.json` + `logistic_pa/card.json`: inputs are the 24-column PA manifest
   above; excluded families explicitly include repertoire/velocity/movement and "k_rate
   level (baseline input; excluded to avoid double-counting)".
2. Grep for `sparse72|final58|production_sparse|184` across all logistic_pa/tree_pa
   JSONs: zero hits.

The 72/58 sets (`production_sparse72`, `production_sparse72_monotone`,
`production_final58_consensus` in `src/Python/features.py` registries) belong to the
**game-level k-rate production model** -- a different grain, different lineage, frozen.
The PA tree shares only domain concepts (discipline rates, park), not registry membership.

## 3. Natural grain and rolling window per feature

- Grain: every feature is **PA-grain**; all of F1-F5 are constant within a
  (game, pitcher, batter-hand) matchup; only the four L3 interaction terms vary per PA
  within the game. `b_*` constant per batter-game; `p_*` per pitcher-game-date;
  `park_k` per (season, home_team).
- Windows: batter = season-to-date (shrunk, 200-PA EB) only. Pitcher = P5 rolling +
  season-to-date, both pre-registered. Park = prior-season only. No P10/P20 at PA grain
  (those remain game-level k-rate conventions).

## 4. Selected versus inherited-by-convention windows

- **By convention (never grid-searched; flagged for future retest in PA record section 5):**
  P5 pitcher rolling window; 200-PA batter EB strength; 500-PA park EB prior.
- **Selected by evidence:** P5-vs-std dual inclusion was pre-registered (no post-hoc
  window choice); F6 rest excluded by 2023-fold ablation; F4 history retained despite
  negative ablation delta (kept as baseline-structure input, -0.0000 redundant-not-harmful).
- Production game-level lineage: P5/P10/P20 convention-first, then stabilization-checked,
  then nested window ablation kept them (`docs/reference/model-card.md`,
  PA record section 5). EB 200-PA "MUST RETEST (sweep 100/150/200/300)" remains open there.

## 5. Why monotone T2 lost

`tree_pa`: T2 = monotone-increasing constraints on the 10 K-tendency rate inputs
(b_hand_rate, b_whiff, b_swstr, b_chase, p_whiff_P5, p_whiff_std, p_swstr_P5,
p_swstr_std, p_chase_P5, p_chase_std), best T1 config otherwise. Mean 2023 fold logloss
**0.517279 vs T1's 0.516918** -- the constraints bound the trees away from the only
nonlinearity the data supports, and the family ablations show why: F2 batter discipline
(+0.000915) and L3 terms (+0.001369) dominate; the tree OOF residual correlates 0.9965
with the P3-log5 OOF residual (registered proxy; fold-fitted L3 was not serialized --
see tree_pa/deviations.md), i.e. the additive-logistic structure already absorbs the
signal. [C2 correction 2026-09-30: previously worded as an L3/P3 residual correlation.]
Monotonicity bought nothing and cost capacity. (Distinct from the production
`sparse72_monotone` member, which won the deployment lane on decision metrics at the
game level -- different experiment, different grain.)

## 6. Was the tree stop rule correctly applied?

**Yes.** Registered stop: "ties/loses to L3 -> retain logistic; complexity escalation
stops." 2024 one-shot: E1 +0.000022 (tree worse), E2 -0.000042 (tree better), both CIs
straddle 0; Brier equally indistinguishable; blend gate failed decisively (corr 0.9965
> 0.85). Verdict recorded: TREE BEATS L3: NO / SURVIVES AGGREGATION: NO / BLEND: NO.
L3 (logistic) retained as the frozen development PA baseline. Three pre-evaluation
construction fixes were logged in `tree_pa/deviations.md` before fitting (card hashed
first) -- process clean. One labeled deviation: fold-fitted L3 models were not
serialized, so the T3 blend gate used a P3-log5 proxy.

## 7. Canonical documents needing Phase 8 updates

| Document | Needed update | Owner |
|---|---|---|
| `CONTEXT.md` PA-overhaul paragraph | Now stale: says ladder "not tested"; Phases 6-8 (P3 promotion, pitcher-prior, L3 logistic, tree kill) have landed | this session (done, see below) |
| `docs/reference/model-card.md` | PA-grain development baseline (L3 logistic) + tree kill should join the lineage section; game-level claims unchanged | PA thread (proposal) |
| `docs/reference/reports/pa_overhaul_phase4_5_record_2026-09-29.md` | Phases 6-8 supersede parts of section 6 "Open items"; needs a SUPERSEDED-in-part note or successor record | PA thread |
| `docs/diagrams/03-modeling-and-evaluation.md` | Add PA-grain research lane (L3 logistic frozen dev baseline; tree killed) as proposed-state | PA thread + this thread reviewed |
| `docs/EXECUTION_BACKLOG.md` | PA-thread PRESENT bullets (Phase 6/7/8 results) | PA thread |
| `docs/adr/` | MLflow mirror ADR (PROPOSED written this pass) | owner accepts/rejects |

## 8. MLflow ADR proposal and object mapping

Confirmed by the tree card's own preflight: DEFERRED-during-experiment, adopt as
**read-only SQLite mirror** over cards/manifests/hashes; cards authoritative; MLflow
failure nonfatal.

**Canonical proposal: `docs/adr/PROPOSED-mlflow-research-mirror.md` (ADR-0007,
filed by the PA thread 2026-09-30).** A draft written in this pass was withdrawn as a
duplicate; ADR-0007 is the single proposal and is strictly more detailed (run identity
`card_sha256[:12] + arm_id`, artifact root `research/offseason_2026/mlflow_artifacts/`
+ `mlflow.db` both gitignored, rollback procedure, security notes, full object mapping
incl. deviations/verdicts tags). Object mapping summary (see ADR-0007 for the binding
table): Experiment = family; Run = card+arm; Params = card grid/folds/gates; Tags =
git/lanes/verdicts/historical_import; Metrics = metrics.json + paired summaries;
Artifacts = reports/manifests copied, bundles/predictions referenced by sha only.
Excluded: Model Registry, aliases, production loading, auto-promotion, remote server.
One writer; db + mirror gitignored; recovery = deterministic re-import from canonical
artifacts. Round-trip + nonfatal-failure tests gate adoption.

Object mapping (mirror, never source of truth):

| MLflow object | Mirrors | Canonical source (unchanged) |
|---|---|---|
| Experiment | research program/phase (`pa-overhaul-2026`) | directory of cards |
| Run | one experiment card (tree_pa, logistic_pa, pitcher_prior, pa1a, pa1b) | `card.json` + `hashes.json` |
| Params | card fields (grid, folds, regularization, gates) | card.json |
| Tags | git head, dirty-path count, population labels, temporal lane (2023-fit / 2024-eval), verdict (PROMOTED/KILLED/STOPPED) | card + report.md |
| Metrics | metrics.json (logloss, brier, calib, slices, paired deltas) | metrics.json / paired_comparisons.json |
| Artifacts | report.md, manifests, reliability slices (copied, read-only) | experiment directory |
| Dataset refs | input paths + sha256 from card inputs | card.json inputs |
| Excluded | model bundles, prediction parquets (referenced by hash, not copied), anything under artifacts/, data/ | stay in place |

Non-goals: Model Registry, aliases, production loading, auto-promotion, remote server,
any write path from production. One writer (this workstation). DB + artifact mirror
gitignored. Round-trip + nonfatal-failure tests gate adoption.

## 9. Answers carried into next phases (no action this pass)

## 10. Addendum -- feature-count reconciliation (Phase 8.6 verification against code)

Durable statement (manifest + code evidence, no reruns):

- Serialized feature columns (L3 manifest `feature_order`): **24** (incl. F6 rest/debut).
- Nonconstant columns: **23** -- `log_pa_prior` is constant 0 in every frame
  (`tree_pa/run_tree.py:162` `np.zeros`; lineage doc confirms the bundle build zeroes
  both seasons). L3 coefficient unidentifiable; LightGBM ignores zero-variance input.
- Actively consumed by L3: all 24 serialized columns (F6 included in the L3 bundle;
  F4's `log_pa_prior` present-but-inert).
- Actively consumed by T1/T2: **22 feature columns + `logit(P3)` baseline = 23 inputs**
  (`run_tree.py:145-169`; F6 dropped).
- Incremental evidence: F2 + L3-terms dominate; F4 negative/redundant; F6 ~0 (excluded
  from tree); park retained by frozen-card rule despite ~0 permutation.
- `log_pa_prior`: **INACTIVE_HISTORICAL_FEATURE** -- retained in historical artifacts
  only; future manifests exclude it unless semantics are repaired under a new
  registered experiment.
- Correction note (card prose, preserved as-is): `tree_pa/card.json` writes "F1-F5
  (16 columns)"; code builds 18 F1-F5 columns (F1 2 + F2 3 + F3 10 + F4 2). The "16"
  matches F1-F3+F5 only. The card is historical evidence and is NOT rewritten; this
  paragraph is the correction record. Comparison validity is unaffected (identical rows
  and columns on both arms).

## 11. Phase 8.6 close-out notes
- Count-distribution experiment (D0-D5) is the registered next frontier (tree report
  "Next authorization (owner)"); specification comes after the MLflow gate.
- 2025 validation lanes A-D per owner message; 2025 must be labeled used-for-selection
  after calibration/policy work.
- OPS-1 may run as a separate thread once this report is checkpointed; path ownership
  is disjoint (src/Python/odds_ledger.py + tests vs research/docs).
