# B1 CLOSEOUT — bf-lane-v1 b1_run_v1 (2026-10-16)

**Verdict: ACCEPT WITH LIMITATION.** The B1 Ridge challenger run is closed
out with three recorded limitations (D1/L2/L3), all of which are remediated
in this closeout and none of which touches a registered number.

## Registered endpoint (primary)

- **Paired count-RPS, B1 − B0** (`C_b1_ridge_vs_b0_empirical`), the single
  predeclared contrast of `b1_registration.json`
  (sha256 `e10ee2c4a9a56ece249ba3f2203762a34a6a524c9dff3b432d4afca43756425d`).
- Delta **−0.028178565433309988** (B1 better), null-centered bootstrap
  p = **0.0004997501249375312**, Holm p identical (family of 1); slate-date
  bootstrap n=2000, seed 20261001, block-stratified, one shared draw stream.
- Pooled dev: B0 1.3303025482 vs B1 1.3021239827 count-RPS over 4,866 dev
  rows / 186 slate dates (block_2024H2 + block_2025H1; confirm_2025H2
  EXCLUDED-NOT-SCORED; 2026 CLOSED).

## Chat 2 reconciliation finding (2026-10-16, read-only)

Every registered result reproduces **exactly** from the persisted artifacts:
identities, inputs, models, per-row forecasts, all aggregates, the bootstrap
replicate matrix, the recenter flags, and career-debut pass-through — max
absolute deviation **4.44e-16** (float64 epsilon on a single aggregate field:
`pooled_dev.b1.count_logscore`; everything else 0.0).
Source: `C:\Users\ckaplinger\MLB-Props-Research\bf-lane-v1\B1_RECONCILIATION_CHAT2.md`
(sha256 `12443c7b1179e72517cc2a2dc90dc74563b8961dd89709802fade179d3c83f9e` —
verify against the lake copy; it is hashed inside `run_manifest.json`).

## Limitations and remediation

### D1 — descriptive CI bug (code defect, FIXED via versioned correction)

`metrics.json → bootstrap.paired_deltas_b1_minus_b0.sq_err.ci95_rmse_scale[0]`
is miscomputed: the runner (lines ~680-684) built the lower bound as
`p2.5(√b1) − p2.5(√b0)` instead of `p2.5(√b1) − p97.5(√b0)`.

| | value |
| --- | --- |
| Stored (wrong lower) | `[-0.7098076573910497, -0.4527807057818549]` |
| **Correct interval** | **`[-0.9848014609216529, -0.4527807057818549]`** |

Remediation: versioned correction `b1_d1_ci95_correction_v1.py`
(CORRECTION_ID `b1-d1-ci95-rmse-scale-v1`) + regression test
`test_b1_d1_ci95_correction.py` (4 tests; deterministic check recomputes the
corrected lower bound from the persisted bootstrap matrix and passes).
**The executed runner `run_b1_ridge_v1.py` is NOT edited** (byte identity
preserved, see L3); `metrics.json` is never rewritten (write-once).

**UNAFFECTED by D1, stated explicitly:** the primary endpoint (paired
count-RPS B1−B0), the paired contrast, the bootstrap p-value
(0.0004997501249375312), the percentile CI on the paired count-RPS delta,
and the gate verdict. The field is labelled "descriptive" in metrics.json
and was never consumed by any decision or registered CI.

### L2 — missing run_manifest.json (CLOSED)

`C:\Users\ckaplinger\MLB-Props-Research\bf-lane-v1\b1_run_v1\run_manifest.json`
added 2026-10-16 — sha256
`37910a98b69177704a8147c2c5e04880a893927c368d598329a674298943b16a`.
Derived ONLY from existing final artifacts (metrics.json config + inventory
cross-checked against disk, tracking_status.json, error log, read-only MLflow
query, filesystem mtimes). No forecast regenerated; no existing output
rewritten. Immutable/write-once; its hash is recorded here and must never be
edited in place.

### L3 — untracked executed scripts (CLOSED)

Both runners committed byte-identical in this closeout commit, verified
against the reconciliation-recorded sha256 values before committing:

| file | sha256 |
| --- | --- |
| `run_b1_ridge_v1.py` | `ead15e2b42144c58f9418df8beff048320e77493af94352815da2a4a7bff30ae` |
| `recover_b1_logging_v1.py` | `5feaaad38bf8b8f702b2f23f9e5e50060879840a4eef8a1d8ad1772a38031d6c` |

No cleanup, no material edit.

## Recenter mass-loss flags

**217 of 4,866 rows (4.5%)** carry `recenter_mass_loss_flag` (dropped mass >
0.01 guard; max 0.42, median 0.0347 on flagged rows). All flagged rows are
renormalized valid PMFs (sum-to-1 max dev 2.22e-16, all 60 support entries
nonnegative); reported, never silently accepted — exactly as registered.

## MLflow failed-then-recovered logging event

1. **FAILED run** `f9403150509d4bc089b1f309a14a4e91` (start/end
   2026-10-16T20:02:17Z): params + metrics logged; config-artifact upload
   failed inside `local_artifact_repo._write_file`; error recorded in
   `b1_run_v1_error_log.json` ("single run; partials preserved; NO silent
   retry").
2. **Recovery** `recover_b1_logging_v1.py` — log-phase-only recovery under
   FINISHED run `52669d842e7448d6873877280991c3c5` (2026-10-16T20:03:47Z):
   `metrics.json` sha asserted equal before/after (byte-untouched), no refit,
   no rescore, no output overwrite; `tracking_status.json` = VERIFIED/verify.
   Verified by Chat 2 (section 5 of the reconciliation).

## Lake path + artifact hashes

Authoritative run dir: `C:\Users\ckaplinger\MLB-Props-Research\bf-lane-v1\b1_run_v1\`
(packet root: `C:\Users\ckaplinger\MLB-Props-Research\bf-lane-v1\`).

| artifact | sha256 |
| --- | --- |
| `metrics.json` | `0453da67f0c37fdddc37cc66492769014b419c0a0d11bbb46ee1d79da74002f8` |
| `b1_per_row_forecasts.parquet` | `a5f0ad81318c25e34d8837ee56d8728db63df4cd56049d8497d126d6880fcb69` |
| `b1_bootstrap_replicates.npy` | `9a2b663119f0403e212a724ff9804dab2dc133d24fbafa2075ad58464e3b895e` |
| `b1_per_date_paired_sums.csv` | `623419cf2a373954c78206e8d18187fdaf2af5e5711d0cd786e0b13612f52904` |
| `models\block_2024H2_ridge.joblib` | `db06405a13d45f6c9975ec743bc8ef773dabfd0010a8cface128615cabe734e5` |
| `models\block_2025H1_ridge.joblib` | `61e3fc1b285f05ce872568dc6366526e6a995f859d3ea7312d7be8fea266c01c` |
| `run_manifest.json` (new, L2) | `37910a98b69177704a8147c2c5e04880a893927c368d598329a674298943b16a` |
| `b1_registration.json` | `e10ee2c4a9a56ece249ba3f2203762a34a6a524c9dff3b432d4afca43756425d` |
| `b0_audit.json` | `a420dda40317b517dcf7d4cfcafee5d9e8877f52299d1e716db5d70071218a69` |

Full inventory (including wrapper config artifact and `retrieved/` copy) is
inside `run_manifest.json`. Input identities (`bf_forecasts.parquet`
`c9c2762f…`, `start_metrics_v2.parquet` `af6814ec…`, `pa_table.parquet`
`e30d8561…`, `build_bf_forecasts.py` `8893918b…`, `kcount_combiner.py`
`94f57a49…`) and `p_bar_sha256` `b9148652…` are recorded in metrics.json
config and re-verified from disk by the reconciliation.

## Bounded scientific conclusion

B1 is a **Ridge-driven recentering of B0's empirical BF PMF** — the stored
BASE empirical pmf37 extended via the frozen combiner and shifted by a
deterministic integer round of (Ridge predicted mean − B0 expected BF), with
a 0.01 mass-loss guard. It is **not a new distributional uncertainty model**:
the uncertainty representation, count integration (k_max 24, milestones
6/8/10/12), p_bar (w=150 log5, identical both arms), folds, and cohort are
all inherited unchanged from the audited B0 lineage (bf-workload-v1). The
registered result — B1 better on paired count-RPS (−0.0282, p_holm 0.0005)
with a pooled ge6 milestone-Brier improvement traded against small ge8/10/12
degradations — is evidence about this recentering construction only, on the
dev blocks (2024-07-01..2025-06-30). confirm_2025H2 remains
EXCLUDED-NOT-SCORED and 2026 stays closed; no promotion, no production
change, and no claim beyond the registered estimand.

## Provenance note on timestamps

All execution/recovery timestamps in `run_manifest.json` are derived from
persisted artifacts (MLflow record, error log, tracking_status.json,
filesystem mtimes) and date the run to 2026-10-16T20:01–20:04 UTC. The
closeout task brief cited an execution timestamp of 2026-10-15T17:35:41Z;
no persisted artifact supports that value, so it is not recorded as a run
timestamp anywhere.
