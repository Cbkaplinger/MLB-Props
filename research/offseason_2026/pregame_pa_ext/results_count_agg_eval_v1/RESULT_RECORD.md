# RESULT RECORD — Question A: exact heterogeneous count aggregation
# (pregame-pa-ext-v2, 2026-10-21)

This is the COMPLETE, unabbreviated result record for the one authorized
execution of the Question A diagnostic. Every hash is FULL. No data is
reconstructed.

## 1. Execution method — how the run occurred while the reviewed CLI was unwired

The reviewed head `38cd4b7` published `run_count_agg_eval()` as a tested
Python function but the CLI `main()` was not wired to call it (it printed
a refusal and returned 2). The execution was performed by an AD-HOC
PYTHON INVOCATION SCRIPT that:

1. imported `count_agg_eval` from the worktree at commit `38cd4b7`;
2. loaded the real frozen artifacts from the lake (preserved ledger, BF
   PMF, realized counts from start_metrics_v2);
3. called `run_count_agg_eval(ledger, bf, realized, out_dir,
   verify_published=True, artifact_paths={...})` with the real paths.

The invocation script was NOT committed and was NOT part of the reviewed
code. The runner logic itself (`run_count_agg_eval` and all called
functions) IS the reviewed implementation. The invocation script is
provided here verbatim for completeness; it is an I/O wrapper, not a
computational change.

### Executed code identity

- Git commit: `38cd4b7d919f1fd07fe9a0907223caafeeaf0b2b`
  (the reviewed head on `research/paext-v2-count-agg-eval`)
- `count_agg_eval.py` LF sha256 (recorded in receipt `code_config`):
  `8d2e92bcc692b2eb7354d9ea28a57f59a1d66031fa9de35686ac7ac215615f7d`
- `count_aggregation_exact.py` LF sha256:
  `7813227fd00c48c03f55629afa66c4fecc93b371b2442adeaa91c8848dbbcddb`
- `adapter.py` LF sha256:
  `276fe0228f149241bdc34473064db1ec8caadd36f2a5d1c57e2a5c189940c164`
- Working-tree state at execution: clean (no uncommitted changes to
  any .py file)
- Invocation script: ad-hoc, uncommitted, provided in this record
- Later CLI-fix commit: NONE (the CLI wiring fix has not been committed;
  the invocation was direct Python, not CLI)

## 2. Receipt chain (full hashes)

| File | sha256 |
| --- | --- |
| receipt_initial.json | `3f01f4469645f275202fca23a0737608b3a1a0b3c36ec0aa6c672cf43236227f` |
| receipt_final.json | `dbcba2c0d8bf9980c06cc44803a61bea8f4e3105465400bc5e6babb550efe53a` |
| count_agg_eval_v1.parquet | `afc94ad74f824b73d29e9069e17f16824786a1e8dda6395213beea64a2afaf34` |
| metrics.json | `df0c49f058d2e092a68071b1f57289e35abd66a58b35ad30f79ba522e89eb42c` |

- `receipt_final.json` chains to `receipt_initial.json` via
  `receipt_initial_sha256 = 3f01f446...` (verified at run time).
- No receipt was repaired in place. The initial receipt was written first
  and never modified.

## 3. Consumed input identities (full hashes)

| Input | sha256 |
| --- | --- |
| preserved_run_ledger | `fd1841e12c19b55b3259935a778c5e8815a0e37b20666b2e53d001d0adb840b8` |
| bf_pmf | `c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679` |
| realized_counts_source | `af6814ec7ea73b4ac941dd52f185139062b987762d639203b867e15bb4817fde` |

## 4. Context identities (full hashes; hashed but NOT consumed by this runner)

| Identity | sha256 |
| --- | --- |
| checkpoint | `d266a1cd108633012e2bdec8c93dd467759fd966191c71aed9d790b74d1c68c6` |
| lineups | `b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b` |

## 5. Output file hashes (full)

| File | sha256 |
| --- | --- |
| count_agg_eval_v1.parquet | `afc94ad74f824b73d29e9069e17f16824786a1e8dda6395213beea64a2afaf34` |
| metrics.json | `df0c49f058d2e092a68071b1f57289e35abd66a58b35ad30f79ba522e89eb42c` |

## 6. Results

### Primary: count-RPS (lower is better)

| Statistic | Value |
| --- | --- |
| Baseline mean count-RPS | 1.3176129559136192 |
| Challenger mean count-RPS | 1.3172796098139778 |
| Paired delta (challenger − baseline) | **−0.00033334609964130735** |
| 95% percentile interval | **[−0.00041920102277617224, −0.00024484405822438606]** |
| Registered p-value (null-centered, B+1 correction) | **0.0004997501249375312** |
| Holm-adjusted p (m=1) | 0.0004997501249375312 |
| Bootstrap n / seed | 2000 / 20261001 |

**Interpretation:** the exact heterogeneous aggregator produces a
**smaller count-RPS** than the registered averaged-binomial (negative
delta = challenger better). The interval is entirely negative. The
registered p-value sits at the 2000-resample resolution floor.

### Supporting: milestone Briers (descriptive, never gated)

| Milestone | Baseline mean | Challenger mean | Delta |
| --- | --- | --- | --- |
| K>=6 | 0.2119267647 | 0.2119031193 | −0.0000236454 |
| K>=8 | 0.1148919736 | 0.1149051114 | +0.0000131378 |
| K>=10 | 0.0352640265 | 0.0352571833 | −0.0000068432 |
| K>=12 | 0.0076345916 | 0.0076300625 | −0.0000045291 |

### Per-start paired scores

| Statistic | Value |
| --- | --- |
| Total paired starts | 4,823 |
| Challenger improved (count-RPS lower) | 3,012 (62.45%) |
| Challenger worsened (count-RPS higher) | 1,811 (37.55%) |
| Tied | 0 |
| Max absolute per-start count-RPS difference | 0.019348 |

### Coverage

| Item | Count |
| --- | --- |
| Eligible development starts | 4,823 (frozen key set verified) |
| Development abstaining starts | 43 |
| Confirmation-block abstaining starts | 16 |
| Full-run abstentions (59 = 57 newcomers + Enns/Hart) | 59 |
| Evaluation PAs | N/A (count-level diagnostic, one row per start) |

### Expected-count checks

| Check | Baseline | Challenger | Max abs arm diff |
| --- | --- | --- | --- |
| Untruncated E[K] mean | 397.7033270 | 397.7033270 | **0.0** |
| Bucketed E[K] mean | 4.56626 | 4.56626 | ~1e-9 |

The untruncated E[K] is a MATHEMATICAL CHECK (identical across arms —
both aggregators preserve the same expected count because they use the
same cycled per-PA probabilities). The registered bucketed outputs are
verified separately. **CORRECTION (2026-10-21):** the earlier summary
described the difference as "dispersion only." The correct statement is
that the two aggregators have **the same untruncated expected count but
different distribution shapes** — the shape difference includes
dispersion, tail behavior, and skewness, not merely variance.

## 7. Invocation script (verbatim, uncommitted)

```python
import sys, json
sys.path.insert(0, r"...\paext-v2\research\offseason_2026")
from pregame_pa_ext import count_agg_eval as ce
from pregame_pa_ext import adapter as ad
import polars as pl
from pathlib import Path

ledger = pl.read_parquet(ad.PAEXT_OUT_DIR / "outputs" / "projected_pa_probs_v1.parquet")
bf = pl.read_parquet(ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet")
realized = pl.read_parquet(ad.BF_WORKLOAD_DIR / "data" / "start_metrics_v2.parquet")
out_dir = ad.PAEXT_OUT_DIR / "diagnostics" / "count_agg_eval_v1"
artifact_paths = {
    "preserved_run_ledger": str(ad.PAEXT_OUT_DIR / "outputs" / "projected_pa_probs_v1.parquet"),
    "bf_pmf": str(ad.BF_WORKLOAD_DIR / "data" / "bf_forecasts.parquet"),
    "realized_counts_source": str(ad.BF_WORKLOAD_DIR / "data" / "start_metrics_v2.parquet"),
    "checkpoint": str(ad.CHECKPOINT_PATH),
    "lineups": str(ad.PREGAME_STATE_DIR / "data" / "projected_lineups_variant_v2.parquet"),
}
res = ce.run_count_agg_eval(ledger, bf, realized, out_dir,
                            verify_published=True,
                            artifact_paths=artifact_paths)
```

## 8. Prohibited actions (none performed)

No confirmation-outcome evaluation, no tuning, no policy change, no
overwriting the original UNACCEPTED output, no Question B implementation,
no historical extension, no coverage-policy change.
