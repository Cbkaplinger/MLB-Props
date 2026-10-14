# RUN VERSION MAP - P1 / BF pilot chain run identities

Point-in-time acceptance evidence, 2026-10-13. One row per run: where it
lives, its recorded run identity, its code identity, and its registration
timestamp WHERE ONE WAS RECORDED. Dashes mean "not recorded at execution
time" (disclosed, not backfilled). `obs <date>` = hash observed and
recorded by this map on 2026-10-13, not by the run itself. External dirs
are under `C:\Users\ckaplinger\MLB-Props-Research\` (private lake).

| Run | Dir | Run identity | Code identity | Registration timestamp |
|---|---|---|---|---|
| p1-harness v1 | `p1-harness\` | no run_version / manifest convention yet; superseded by v2 (opening-day prior + labeling corrections) | `reports\run_metadata.json` code_sha256: build_features 9302e4fb...5199520, build_pa_table 2017597c...73efecb, fit_models 7bd58f01...e04b8e | - (none recorded; predates the manifest convention) |
| p1-harness-v2 | `p1-harness-v2\` | run_version "p1-harness-v2"; manifest.json + run_metadata.json with data_sha256, eval_key_identity_sha256 da1d29d4...6ca2d9, dev_key_identity_sha256 1330d0cd...514376 | scripts_sha256 (recorded in-run): build_features a072d82b...4d9f82, build_pa_table b17748ef...3c0cadc, fit_models 4180e7d3...be04b8e | 2026-10-13T04:23:45+00:00 (timestamp_utc in manifest.json) |
| overnight-p1 | `overnight-p1\` | run_manifest.json ("run": "overnight-p1", output_file_sha256 map; experiment_config.json sha 860d7774...51a67); status: DESIGNED, dependent fits STOPPED pending fixed-prior remediation | no in-run code-hash block; scripts preserved in `overnight-p1\scripts\` (obs 2026-10-13: s0_verify 3299a076...b09c969, s0b e457a29f...786d0770c, s0c 8c7d3d0d...768576eb, s1 7b461877...3838af, s5 fec9343b...e351d1cc9, s6 9ddbefd5...d390d53) | generated_utc 2026-10-13 (date precision only) |
| overnight-p2 (v3, 2022-warm-up ruling) | `overnight-p2\` | run_identity.json + run_manifest.json; run_identity_sha256 6a62d8ed...c6def2; features_v3.parquet sha 163ad433...b7e8f8 | scripts hashes recorded in-run (run_identity.json): build_features 920186f5...e4be2219, build_pa_table e778f278...82f0c, run_ladder 9ceeeb09...d17d20cc, run_lgbm f602907a...12aeff9, + others | created_utc 2026-10-13 (date precision only) |
| pilot (BF A/B integration forecast + seal + scoring) | `seal-package-preflight\` + `bf-ab-forecast-2026-cand5\` + `bf-bundle-2026-corr-20261012_132811\` + scoring dirs below | seal_manifest.json status PREPARED-NOT-SEALED, bound_to_source_commit b0540143...a70350; bundle c7ff78b1...76a6fcd; forecast arrays A 16c31bfb...f0f116, B ceb1dca3...f759e1d; population 134 forecasted (11 usable-B) | executed working bytes recorded in-run: run_bf_reconstruct_2026 5f66d516...0226a, run_bf_preflight_2026 0913a37f...ff914d, run_bf_ab_forecast_2026 921f7e5e...af13c35 | created 2026-10-12/13 (per bf-closure-record-2026-10-13; seal manifest carries no timestamp field) |
| scoring v1 (of the pilot) | `bf-ab-score-2026\` | scoring_report.json sha 93b4338d...73fde9, status DELIVERED-suspected (55-row actual_K undercount; superseded) | runner not version-controlled at execution time; "scoring code used" record `scoring_code_used.txt` sha 82d76b55...54a2b (line-content identical to the recovered runner, CRLF vs LF bytes) | - (none recorded) |
| scoring v2 (of the pilot) | `bf-ab-score-2026-v2\` | scoring_report_v2.json sha b5bf8dd5...ad020, status DELIVERED-superseded | runner exists only as unversioned archive copy `runner_executed_v2_archive.py` sha 6b8cecf2...24bc4a (byte-identical to the recovered `run_bf_ab_score_v2.py`; archived 2026-10-13 under `archived-scoring-sources\`) | - (none recorded) |
| v3 scoring | `bf-ab-score-2026-v3\` (canonical) + `handoff-v3\` (byte-identical handoff) | scoring_report_v3.json sha 26c0a247...bc192, status DELIVERED (complete pitcher-game actual_K; adds RMSE + milestone Brier) | producing runner `run_bf_ab_score_v3.py` sha 949e4352...d68afb, committed at 7d0e8c860101d178ad2f17c5e17f3ae1f4fe785f | delivered 2026-10-13 (per MANIFEST.txt "created 2026-10-13") |
| pregame-state-v1 (base report) | `pregame-state-v1\` | report.json ("card": "pregame-state-v1"; window 2024-07-01..2025-12-31, 7,194 starts / 272 slate dates; REGISTERED VARIANT, pitcher = realized first pitcher of record) | scripts observed 2026-10-13 (not run-recorded): run_pregame_state_comparison 67a5e27f...1325b4, build_projected_lineups f247b4b7...f72d | created 2026-10-13 (date precision only) |
| pregame-state-v1 correction v2 | `pregame-state-v1\` | report_v2.json (correction_version 2, same population; v2 unique-bijection lineup variant registered in preregistration_variant_v2.json) | run_pregame_state_correction_v2 ea2eaad2...20494 (obs 2026-10-13), build_projected_lineups_variant_v2 dba32862...bf6c9d (obs 2026-10-13) | created 2026-10-13 (date precision only) |
| pregame-state-v1 report v3 | `pregame-state-v1\` | report_v3.json (report_version 3; 2026 CLOSED - no 2026 rows scored or loaded by any v3 file; 7,194 starts incl. unique variant) | run_pregame_state_v3 1cb3bc5d...e07db (obs 2026-10-13) | created 2026-10-13 (date precision only) |

## Notes

- The p1-harness-v2 data artifacts consumed by this suite are sha256-pinned
  in `p1_harness/conftest.py` (EXPECTED_ARTIFACTS) and byte-verified before
  every integration-lane read.
- The recovered scoring sources (`run_bf_ab_score.py`, content-equivalent
  to the v1 "scoring code used" record; `run_bf_ab_score_v2.py`, byte-exact
  executed v2) are archived outside the repo under
  `C:\Users\ckaplinger\MLB-Props-Research\archived-scoring-sources\` with
  PROVENANCE.md; they are NOT in the publication set and NOT wired into any
  current runner (v3 at 7d0e8c8 is the canonical scorer).
