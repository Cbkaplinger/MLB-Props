# SUPERSEDING PREFLIGHT RECORD — count-PMF calibration v3 (2026-10-27)

## Supersession & Lineage

This receipt **supersedes** both:
1. `preflight_calibration_v2.md` (git-blob LF SHA-256 `f703dea68eed7cf4093c1c7823c3967de96fff522ff1c8ffbf81fd0b91328f85`; working-tree CRLF SHA-256 `469671637f5b29b5bf2ac85c521a78a3448e1877711536f18469944baa0091d4`), which described commit `3291fc539d05f527953bdca92c83ae0991a84773`; and
2. `preflight_calibration_v1.md` (SHA-256 `9962adf5e0114fb972e1bec1a4595c5363351385e95e5f98115c7e82caa919e1`), which described commit `07ef1a5ac67368e698adaf7e57f76859a573564e`.

**Clarification on historical receipt preservation:** Neither `preflight_calibration_v1.md` nor `preflight_calibration_v2.md` (nor `calibration_execution_manifest_v2.json` / `calibration_execution_manifest_v3.json`) was edited or overwritten. When `preflight_calibration_v2.md` stated that the "git compression" explanation in `v1` was "corrected," that correction was recorded **only inside `v2` (and carried forward here in `v3`)** while leaving `preflight_calibration_v1.md` byte-identical on disk (`9962adf5...`).

| Item | Value |
|---|---|
| Worktree path | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2` |
| Branch | `research/count-pmf-calibration-v1` |
| Target computational commit | `e34213a25e381a6359739573c6e41cde12b5d1ac` |
| Superseded commit (`v2` receipt) | `3291fc539d05f527953bdca92c83ae0991a84773` |
| Superseded commit (`v1` receipt) | `07ef1a5ac67368e698adaf7e57f76859a573564e` |
| Base merge commit (`origin/main`) | `b4dd5d9d816599a5991e10f83661fe586de5e01d` (merged PR #34 head `d6ce42a73011ef11f0198a624f0572c88214f887`) |
| Superseded manifests | `calibration_execution_manifest_v2.json` (`35347a47…`), `calibration_execution_manifest_v3.json` (`5c1f272b…`) |
| Current manifest | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\calibration_execution_manifest_v4.json` (`d32409624549a337d15ffef2bd659378b12121a08d86f1a01fe65d9ab953bb80`) |

---

## Scoped Secondary-Reporting Defects Repaired at `e34213a25e381a6359739573c6e41cde12b5d1ac`

The primary `count-RPS` metric, bounded scalar optimizer, `GuardedEvaluationLoader` disk-persistence gate, cohort hashes, and slate-date bootstrap were untouched. Only the two secondary-reporting defects identified in the Architect's review of `3291fc5` were repaired:

1. **Defect 1 — Full-CDF accumulation axis (`count_pmf_calibration_runner.py:283-287`):**
   - **Cause at `3291fc5`:** `F_frozen_all` and `F_cal_all` had shape `(n_eval_starts, 24)` and called `np.cumsum(..., axis=0)`, which summed across starts rather than across strikeout count buckets `k = 0..23`.
   - **Fix at `e34213a`:** Changed both calls to `np.cumsum(..., axis=1)` so each start's 24-bucket PMF is accumulated across `k = 0..23` into a valid per-start CDF in `[0, 1]` with `F(23) = 1.0`, and then averaged across starts (`F_*_all[:, k].mean()`).
   - **Regression test (`test_count_pmf_calibration_runner.py:238-334`):** `test_runner_full_cdf_bucket_axis_and_row_order_invariance` uses multiple starts with distinct hand-checkable PMFs, verifies all 24 buckets against exact hand-calculated CDF averages, checks bounds in `[0, 1]`, monotonicity across `k`, `F(23) = 1.0`, and row-reordering invariance.

2. **Defect 2 — Own-line LL/Brier event consistency and deterministic half-line rounding (`count_pmf_calibration_runner.py:239-244, 302-322` & `card_count_pmf_calibration_2026-10-24.md:171-177`):**
   - **Cause at `3291fc5`:** `own_line_ll_*` and `own_line_brier_*` computed `p_over_f = mk.model_p_over(pmf_f, mean_f)` and `p_over_c = mk.model_p_over(pmf_c, mean_c)` against `o = 1.0 if k_real > mean_f else 0.0`. Whenever calibration moved `mean_c` across an integer boundary relative to `mean_f` (e.g., `mean_f = 4.8` $\rightarrow$ $K \ge 5$, `mean_c = 5.2` $\rightarrow$ $K \ge 6$), `p_over_c` priced a different event from both `p_over_f` and the outcome indicator `o`. In addition, Python `round(mean + 0.5) - 0.5` used banker's rounding on exact integers.
   - **Fix at `e34213a`:** Defined one explicit, deterministic half-line rule from the frozen forecast:
     `_own_half_line(pmf_f) = max(0.5, float(np.floor(mean_f + 0.5) - 0.5))`
     Used `_own_half_line(pmf_f)` consistently in both `threshold_reliability` and `own_line_ll_*` / `own_line_brier_*`, evaluating both `mk.model_p_over(pmf_f, t_own)` and `mk.model_p_over(pmf_c, t_own)` at the identical start threshold `t_own` against the shared outcome label `o = 1.0 if k_real > t_own else 0.0`. Reconciled the exact formula in `card_count_pmf_calibration_2026-10-24.md` §9.
   - **Regression test (`test_count_pmf_calibration_runner.py:337-402`):** `test_runner_own_line_event_consistency_across_integer_boundary` constructs a cohort where `mean_f = 4.80 < 5.0 < mean_c` (`realized_k = 5`), proves `p_over_c` at `t_own = 4.5` ($K \ge 5$) differs from the crossed-boundary event ($K \ge 6$), and verifies exact agreement of `own_line_ll_*` and `own_line_brier_*` with independent calculations at `t_own = 4.5`.

---

## Code & Card Identity Table at Computational Commit `e34213a25e381a6359739573c6e41cde12b5d1ac`

| File (relative to repo root) | Git Object OID (SHA-1) | Git-Blob LF SHA-256 | Working-Tree Bytes SHA-256 | Working-Tree Line Endings | Superseded `3291fc5` Working-Tree SHA-256 |
|---|---|---|---|---|---|
| `research/offseason_2026/pregame_pa_ext/count_pmf_calibration_runner.py` | `65b9902c127f9d8e74c7968a67ae1f1cdaed999b` | `983f1135eba2a9668ea8105530ebd911134c76f8e9a7874b0ff816ecc46fcc75` | `f06667ef64b451ae48147cf1d8fe434f2c9b676c49c5fd0205100bf1de5b5d35` | CRLF | `50d9f98879e25b295f04fefd9d588803de6ae1751d9d8b470a4683737816161a` |
| `research/offseason_2026/pregame_pa_ext/count_pmf_calibration.py` | `352b568318e797572450742a2ef683e095671038` | `e8b9e26afa8e426d2120072b50d66cdb7cb7815fdd542b44f267c06f9e368a64` | `e8b9e26afa8e426d2120072b50d66cdb7cb7815fdd542b44f267c06f9e368a64` | LF | `e8b9e26afa8e426d2120072b50d66cdb7cb7815fdd542b44f267c06f9e368a64` |
| `research/offseason_2026/pregame_pa_ext/card_count_pmf_calibration_2026-10-24.md` | `8b4ea6bb04c37bffd7032da97cf410e20f369396` | `be6c3f4ce41f0365a73f689e23cdf1ed1db7bfda0a367112039b05bff0e4f7b3` | `be6c3f4ce41f0365a73f689e23cdf1ed1db7bfda0a367112039b05bff0e4f7b3` | LF | `115ceb3746b9077d085fcac37a1b660eeab79f890011e4dcacfbaa0ec1d4fb6a` |
| `tests/test_count_pmf_calibration.py` | `c489ac2bb44bfbcd30c6aa8cf8f036fed2ccb113` | `11b9bb305556de4c8955846d432f252ec194258963c1e748012a04fea56c9831` | `11b9bb305556de4c8955846d432f252ec194258963c1e748012a04fea56c9831` | LF | `11b9bb305556de4c8955846d432f252ec194258963c1e748012a04fea56c9831` |
| `tests/test_count_pmf_calibration_runner.py` | `248791a10e87db2db1df0f6374027c80dd91ebf9` | `a0bc4a4625a35b6bc7129218a4b3f5c26f86b8e9c2a6cd7a3c066f2407c1956c` | `2b770600727f9844f03de75a0abe60b65d5bc973ad4a649310faa89d8a021fac` | CRLF | `28cfd33fd9ab773d4ae007c9448d8e6297aa05058324a8a2f54049cba33e8dd5` |
| `research/offseason_2026/pregame_pa_ext/preflight_calibration_v1.md` (preserved) | `174e3b7f5bf5556355355c1572248db8c02d09ae` | `9962adf5e0114fb972e1bec1a4595c5363351385e95e5f98115c7e82caa919e1` | `9962adf5e0114fb972e1bec1a4595c5363351385e95e5f98115c7e82caa919e1` | LF | `9962adf5e0114fb972e1bec1a4595c5363351385e95e5f98115c7e82caa919e1` |
| `research/offseason_2026/pregame_pa_ext/preflight_calibration_v2.md` (preserved) | `606f7fdfbc4159239584fab5e04bcff38125f38b` | `f703dea68eed7cf4093c1c7823c3967de96fff522ff1c8ffbf81fd0b91328f85` | `469671637f5b29b5bf2ac85c521a78a3448e1877711536f18469944baa0091d4` | CRLF | `469671637f5b29b5bf2ac85c521a78a3448e1877711536f18469944baa0091d4` |

---

## Registered Input & Cohort Verification (Unchanged, Zero Outcome Evaluation)

| Artifact / Cohort | Count / Scope | Full SHA-256 | Verified Match |
|---|---|---|---|
| `count_agg_eval_v1.parquet` (registered PMF input) | 4,823 dev starts | `afc94ad74f824b73d29e9069e17f16824786a1e8dda6395213beea64a2afaf34` | ✓ |
| `h3_raw_checkpoint.json` (raw file bytes) | pin `176fb18b…` | `d266a1cd108633012e2bdec8c93dd467759fd966191c71aed9d790b74d1c68c6` | ✓ |
| `bf_forecasts.parquet` (registered BF workload) | pregame BF PMF | `c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679` | ✓ |
| `projected_pa_probs_v1.parquet` (preserved ledger) | 64,215 slot rows | `fd1841e12c19b55b3259935a778c5e8815a0e37b20666b2e53d001d0adb840b8` | ✓ |
| `start_metrics_v2.parquet` (registered realized K) | start labels | `af6814ec7ea73b4ac941dd52f185139062b987762d639203b867e15bb4817fde` | ✓ |
| Calibration cohort (`block_2024H2`) | `n = 2,314` unique starts | `d38b10aae3fe747206b2d33588cb2729306206a91724f72b9ffc97a96522edf0` | ✓ |
| Evaluation cohort (`block_2025H1`) | `n = 2,509` unique starts | `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7` | ✓ |
| Calibration / evaluation key overlap | `0` shared starts | — | ✓ |
| `confirm_2025H2` rows in `count_agg_eval_v1.parquet` | `0` rows | — | ✓ |
| Output directory `count_pmf_calibration_v1/` exists? | `False` (not executed) | — | ✓ |

---

## Permitted Synthetic Test Execution Receipt at `e34213a`

- **Calibration unit + runner integration suite (including the 2 new numerical regression tests):**
  - Command: `python -m pytest tests/test_count_pmf_calibration.py tests/test_count_pmf_calibration_runner.py -q`
  - Result: **49 passed, 0 failed, 0 skipped** (`35` in `test_count_pmf_calibration.py`, `14` in `test_count_pmf_calibration_runner.py`) in `23.83s`.

---

## Exact Registered Invocation (DO NOT EXECUTE WITHOUT CHAT 2 VERDICT + OWNER AUTHORIZATION)

```powershell
C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\.venv\Scripts\python.exe -c "
import sys; sys.path.insert(0, r'C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2\research\offseason_2026')
from pregame_pa_ext.count_pmf_calibration_runner import run_count_pmf_calibration
import polars as pl
pmfs = pl.read_parquet(r'C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\count_agg_eval_v1\count_agg_eval_v1.parquet')
result = run_count_pmf_calibration(
    pmfs,
    r'C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\count_pmf_calibration_v1',
    expected_cal_hash='d38b10aae3fe747206b2d33588cb2729306206a91724f72b9ffc97a96522edf0',
    expected_eval_hash='f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7',
    n_boot=2000,
    seed=20261001,
)
import json; print(json.dumps(result['metrics'], indent=1, sort_keys=True))
"
```

## STATUS: AWAITING CHAT 2 CONSOLIDATED READINESS VERDICT (NOT EXECUTED)
