# Execution packet: temporal_robustness_v1 (R1/R2 - exact periods)

STATUS: AUTHORIZATION-READY, NOT AUTHORIZED. Every factual claim below was
checked against the code at the frozen checkpoint (2026-11-04). Approval
flow: Chat 2 packet review -> explicit owner approval -> single execution
of the exact command in this packet. The ack token
`EXECUTE-TEMPORAL-ROBUSTNESS-V1` is a technical gate only and is NOT
authorization. Card: `docs/adr/PROPOSED-temporal-robustness-evaluation.md`
(specification resolved 2026-11-04).

## Code checkpoint (frozen during review)

Executable frozen at the commit introducing this packet on
`research/lgbm-multiclass-v1` (SHA named in the PR #59 dashboard). Module
SHA-256 identities at that checkpoint:

| Module | SHA-256 |
|---|---|
| temporal_robustness_evaluation.py (runner, repaired; verified on-disk in the designated execution worktree at `7949ad2`) | `3c7b1468ab4fbb88ec229815e30e41d4facb68b63ddc2d5d914f346e434655cd` |
| platoon_comparison.py (candidate fit + softmax, imported) | `8136e1a81f03ff188666a1eb5e7bd184fc41bfdb92a678d7c36b4dc904c2237f` |
| platoon_features.py (platoon-features-v1) | `ccc56ecac9aed45026c32bb5ce9faa69f07fdfcc2eefd831b8e7607ca46e7122` |
| binary_k_comparison.py (helpers, imported) | `3ad1ccedce6eb6122a017b38b455cdc88d7e0320a0d56dba0d7d0a8b2aefe7ad` |
| adapter.py | `adfa7283d2150abe05ea480f86451a54cb7f550e8e87d798d8940e3fef5a4e47` |

Runner identity is the LF file currently materialized in the designated
execution worktree (wtsc). Runtime receipt records its actual bytes.
Other module pins retain their individually verified byte identities.

| m0_multiclass.py | `5afe972b4f1c8921f2a87b53af4e1783384ec09fb880ab44328d0b3c18e809fd` |
| workload_comparison.py (pooled-BF37 construction source) | `c0b391bb818f393524d6732946bff41fd4df9d9c0c350e7480e2ff437581f90c` |
| kcount_combiner.py | `94f57a49c0996df5147fb961a085fd229d0ba0e3903c6da0ced9f2d3b670f18f` |
| statcast_event_bridge.py | `5781b3cf83f3d9780fd41cc375b2d29a4a9968bb4a2db996b29ab489a099f4dc` |
| forecast_states_v2.py | `7ec56566c9382ecd8d678338817537f35f2b018f17b756931aa1e0d59a9b356b` |
| baseline_ladder.py | `af81e313be3f11c3a257f64871879d21643e1a18ca4356407e86440a738a55d0` |

adapter/m0/workload/kcount/binary_k hashes are byte-identical to the
verified binary-K and platoon runs' pins. Any code change during review is
a new checkpoint, not this packet.

## What runs (exact periods, identical-arm populations)

ONE invocation evaluates the retained candidate (12-feature
multinomial-plus-platoon) against the 8-feature multinomial-plus-W0
control across TWO hardcoded periods, plus ONE machinery-identity anchor:

- **R1:** fit `2023-03-30..2024-06-30` -> score `2024-07-01..2024-09-30`.
  Scored actual PAs derive from the labeled PA source (side attached via
  the uniqueness-validated (game_pk, pitcher) request mapping).
- **R2:** fit `2023-03-30..2024-12-31` -> score `2025-01-01..2025-06-30`.
  Scored actual PAs come from the pinned registered 2025H1 assessment
  artifact.
- **Anchor (machinery identity, gates everything):** the registered
  8-feature multinomial-plus-W0 recipe refit on `2024-05-01..2024-12-31`
  and scored on the registered 2025H1 cohort MUST reproduce the accepted
  per-start reference (column `rps_w0_pooled`, sha below) within 1e-12
  BEFORE any period contrast is reported. Anchor per-start evidence is
  written before the gate so a mismatch is diagnosable.

Both arms in each period are fit on the SAME fit rows and scored on the
SAME matched-PA population (asserted). Fits: 2 candidate + 2 control + 1
anchor = 5 multinomial fits total (fixed recipe, no tuning). Feasibility
per period (>= `--min-fit-date-clusters` distinct fit-window date
clusters [packet-pinned 60; verified 277/365], nonempty score dates,
strict chronology, score-class compatibility) is verified BEFORE any
model fit.

## Structural access limits (hard constants; R3/2026 inaccessible)

The score windows END `2025-06-30` (hardcoded constants verified at
entry). The runner refuses any period whose fit or score end reaches the
R3 confirm partition (`2025-07-01+`) or the hard scored-date limit, and
refuses any scored date at/after `2025-07-01`. R3 (2025-07-01..2025-09-28)
and 2026 are structurally inaccessible to this evaluation path; rows
beyond the score windows are never read into a scoring path.

## Metrics (declared)

Per period: per-PA multiclass log loss on the identical matched-PA
population; contrast statistic = PER-START MEAN (each start equally
weighted, PAs equally weighted within a start); paired slate-date
bootstrap 2,000 draws seed 20261001. Practical threshold 0.0005 nats.
K-count non-degradation guard per period: 0.002 point-estimate margin
(NOT a noninferiority claim; CI as context). Secondary: classwise log
loss / Brier, K RPS means. No tuning, no calibration.

## Identity pins and enforcement mechanisms

| Input | Path / source | Identity mechanism |
|---|---|---|
| PA source | `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet` | File SHA-256 `1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff` - ENFORCED pre-decode (exit 1) |
| Projected lineups | `C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet` | File SHA-256 `b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b` - ENFORCED pre-decode (exit 1) |
| Assessment outcomes (R2) | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet` | File SHA-256 `464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa` - ENFORCED pre-decode (exit 1) |
| **Reconstruction reference (anchor)** | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1\workload_per_start_v1.parquet` (accepted multinomial-plus-W0 per-start artifact, column `rps_w0_pooled`) | File SHA-256 `ae971758b70e1649e28046a8180d375872ad0172f9c8b5cc03ab74e8dfa85f79` - **ENFORCED pre-decode (exit 1)** |
| Cohort keys (n=2,509, 2025H1 - applied to the anchor and R2 paths ONLY) | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet` | Sorted-key CONTENT hash `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7` - ENFORCED before feature construction (refusal). The file's byte hash is a different quantity, NOT the pin. R1 carries its OWN eligible key set: the R1 score-window request keys from the pinned lineups input (outcome-independent; identity hash + count recorded in the report/receipt) |
| Raw Statcast 2023 (NEW - labels the declared 2023 fit window) | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2023\statcast_2023_regular.parquet` | SHA-256 `b9f9db9923badca17e551cf23be8429bfba984361732a8911bf0d68a40d5285f` - RECORDED (procedural). REVISED ACCESS SCOPE: without this file the 2023 fit rows cannot be labeled and the declared 2023 training history silently shortens; the runner now refuses any fit-window year with raw observations but zero eligible labels |
| Raw Statcast 2024 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet` | SHA-256 `de78a1893aa21e305153f5594987f85b40e4bc0cf572484e995a1416b3c49b33` - RECORDED in the receipt (procedural) |
| Raw Statcast 2025 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet` | SHA-256 `cb072ff830959374ae2f8a8d804a0093e77b2cf0d898fda046b44605d5c31aad` - RECORDED (procedural) |

All six pinned files were re-hashed on disk 2026-11-04 and match; the
cohort content hash was recomputed from the 2,509 keys and matches.
Projected-lineups coverage for BOTH score windows verified (88 + 98
observed date clusters; date-column inspection only, no outcome reads).

## Destination

`C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\temporal_robustness_v1` - fresh write-once directory. Evidence saved: `receipt_initial.json` (immutable), `receipt_final.json`, `temporal_robustness_report.json` (per-period results + coverage reconciliation + training-label coverage by year + feasibility + anchor reconstruction + R1 cohort identity), `temporal_per_start_R1.parquet` / `temporal_per_start_R2.parquet`, `k_pmf_per_start_R1.parquet` / `k_pmf_per_start_R2.parquet` (both arms, 24 buckets), `keyed_pa_probabilities_R1.parquet` / `keyed_pa_probabilities_R2.parquet` (both arms' full class-probability vectors), `anchor_per_start.parquet` (written BEFORE the anchor gate), `failure_record.json` on any exception (then re-raise).

## Command (single line, copy-paste ready; execution only after approval)

```
python research/offseason_2026/pregame_pa_ext/temporal_robustness_evaluation.py --pa-source "C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet" --lineups "C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet" --assessment "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet" --raw-events "C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2023\statcast_2023_regular.parquet,C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet,C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet" --out-dir "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\temporal_robustness_v1" --execution-ack EXECUTE-TEMPORAL-ROBUSTNESS-V1 --cohort-keys "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet" --expected-cohort-hash f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7 --reconstruction-reference "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1\workload_per_start_v1.parquet" --expected-reconstruction-sha256 ae971758b70e1649e28046a8180d375872ad0172f9c8b5cc03ab74e8dfa85f79 --expected-pa-sha256 1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff --expected-lineups-sha256 b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b --expected-assessment-sha256 464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa
```

All 15 flags verified against the CLI argparse (`--help`, 2026-11-04);
none missing, none extra. `--min-fit-date-clusters` is NOT passed (the
packet-pinned default 60 applies; the registered source provides 277/365
fit-window date clusters).

## Refusals and stop conditions (exhaustive)

- Wrong/missing execution ack: exit 2, zero reads, zero writes.
- Any of the four file-byte pins mismatched: `INPUT IDENTITY MISMATCH`,
  exit 1, zero writes.
- Cohort content hash mismatch, duplicate/null cohort keys: refusal
  before feature construction.
- Period feasibility failure (too few fit date clusters, empty score
  window, non-chronological, score-class incompatibility): refusal BEFORE
  any model fit; failure evidence preserved.
- Anchor reconstruction gate failure (keys differ, or max per-start
  |RPS diff| > 1e-12): anchor per-start evidence preserved, report and
  receipt aborted, failure record written, non-zero exit. Never tuned
  away.
- Structural-limit violation (any period touching the R3 partition or
  the hard scored-date limit): refusal at entry, independent of data.
- Duplicate actual-PA identities, empty scored/matched populations,
  matched PA with a class outside the fitted class set, a start without
  9 usable slots, ambiguous side mapping: refusal.
- Any exception: `failure_record.json` then re-raise.
- On any refusal or failure: STOP. Evidence preserved; no altered
  tolerance, no silent input substitution, no unapproved retry.

## Reporting rules (pre-declared in the card)

Per-period statistical direction and practical magnitude are reported
separately: CI entirely below zero favors the retained candidate;
entirely above favors the 8-feature control; overlapping zero is
inconclusive. A mean log-loss improvement below the declared practical
threshold (0.0005 nats) does not justify the added feature family
regardless of CI direction. The K-count acceptance guard is the 0.002
point-estimate margin (NOT a statistical noninferiority claim).
Promotion is never automatic. The anchor gate must pass before any
contrast is reported.

## Explicitly out of scope (deferred)

R3 (2025-07-01..2025-09-28) and 2026 are structurally inaccessible; a
future R3 evaluation requires a specific new owner authorization. No
tuning, no new features, no calibration, no SHAP, no new learner, no
taxonomy/workload/aggregation change. The `m0.apply_multinomial`
two-class softmax repair and any change to the reviewed
`workload_comparison.py` remain DEFERRED (this runner uses the
identical-softmax helper for any observed class count). No MLflow
logging, no follow-up runs, no subgroup analyses.

## Limitations carried into any result

Development evidence on the registered source; R1/R2 score windows are
EXPOSED (prior use disclosed in the card) - NOT fresh final tests;
matched-matchup PA coverage limitation carries over; 2026 untouched.
