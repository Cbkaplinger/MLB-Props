# SUPERSEDING PREFLIGHT RECORD — count-PMF calibration v2 (2026-10-27)

## Supersession & Lineage

This receipt **supersedes** `preflight_calibration_v1.md` (SHA-256 `9962adf5e0114fb972e1bec1a4595c5363351385e95e5f98115c7e82caa919e1`), which remains preserved untouched in this directory as the historical record for commit `07ef1a5ac67368e698adaf7e57f76859a573564e`.

| Item | Value |
|---|---|
| Worktree path | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2` |
| Branch | `research/count-pmf-calibration-v1` |
| Target computational commit (HEAD) | `3291fc539d05f527953bdca92c83ae0991a84773` |
| Intermediate reconciliation commit | `2c716a4e5a4e6383183d569080cc74fb44b0415b` |
| Superseded preflight commit | `07ef1a5ac67368e698adaf7e57f76859a573564e` |
| Base merge commit (`origin/main`) | `b4dd5d9d816599a5991e10f83661fe586de5e01d` (merged PR #34 head `d6ce42a73011ef11f0198a624f0572c88214f887`) |
| Superseded manifest | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\calibration_execution_manifest_v2.json` (`35347a47ef65d4f729287898a9eda35524f776c3faa7354313e93393a6a4bdf7`) |
| Current manifest | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\calibration_execution_manifest_v3.json` (`5c1f272b6b4bfeb9eae9ccaba54f4515575bde86abd6650b68524934aa61bf00`) |

---

## Correction of Hash Convention Note in `preflight_calibration_v1.md`

`preflight_calibration_v1.md` stated: *"Git-blob hashes (committed tree) differ from working-tree SHA-256 because git stores compressed objects; the working-tree SHA-256 is the contract identity."*

**Correction:** Git zlib compression applies only to loose/packfile storage on disk and never alters extracted blob content hashes. The actual distinctions across the three identities recorded below are:
1. **Git Object OID (SHA-1):** SHA-1 over the header-prefixed LF payload `"blob <byte_length>\0" + lf_bytes` (`git rev-parse HEAD:<path>`).
2. **Git-Blob Content SHA-256 (LF):** SHA-256 over the raw extracted git blob bytes (`git show HEAD:<path>`), which use LF (`\n`) line endings.
3. **Working-Tree File SHA-256:** SHA-256 over `Path(<path>).read_bytes()` in the Windows checkout. When a file has CRLF (`\r\n`) line endings in the working tree (`core.autocrlf=true`), its working-tree byte SHA-256 differs from the LF git-blob SHA-256; when a file has LF line endings in the working tree, the two SHA-256 digests are identical. Note that `count_pmf_calibration_runner._code_identity()` (`lines 61-68`) computes `hashlib.sha256(Path(__file__).read_bytes()).hexdigest()`, which records the **working-tree bytes SHA-256** in `receipt_initial.json` and `receipt_final.json`.

---

## Code & Card Identity Table at `3291fc539d05f527953bdca92c83ae0991a84773`

| File (relative to repo root) | Git Object OID (SHA-1) | Git-Blob LF SHA-256 | Working-Tree Bytes SHA-256 | Working-Tree Line Endings | Superseded `07ef1a5` Working-Tree SHA-256 |
|---|---|---|---|---|---|
| `research/offseason_2026/pregame_pa_ext/count_pmf_calibration_runner.py` | `2c42672cfaedd3ed2f81c114ea3a61e42c2b229a` | `10ba60e5f61765b55daee7c6921036f23682df66af3a7343eae7d750b519abaa` | `50d9f98879e25b295f04fefd9d588803de6ae1751d9d8b470a4683737816161a` | CRLF | `1e2c82c2f7f386db2e0db5867f95ef2cd2d350947a76b8ec70fa6a24e41f752a` |
| `research/offseason_2026/pregame_pa_ext/count_pmf_calibration.py` | `352b568318e797572450742a2ef683e095671038` | `e8b9e26afa8e426d2120072b50d66cdb7cb7815fdd542b44f267c06f9e368a64` | `e8b9e26afa8e426d2120072b50d66cdb7cb7815fdd542b44f267c06f9e368a64` | LF | `409a17be49aba885d42c57ad15cf1ded00c3ae74374cb51c54025e736ec90059` |
| `research/offseason_2026/pregame_pa_ext/card_count_pmf_calibration_2026-10-24.md` | `fb0be495639f2419e6b449294435370f77479415` | `115ceb3746b9077d085fcac37a1b660eeab79f890011e4dcacfbaa0ec1d4fb6a` | `115ceb3746b9077d085fcac37a1b660eeab79f890011e4dcacfbaa0ec1d4fb6a` | LF | `b12a3d059b3a65bb33b65e14260bd0a4fc2cbbccb9af69c07af2e9dcf5fe9343` |
| `tests/test_count_pmf_calibration.py` | `c489ac2bb44bfbcd30c6aa8cf8f036fed2ccb113` | `11b9bb305556de4c8955846d432f252ec194258963c1e748012a04fea56c9831` | `11b9bb305556de4c8955846d432f252ec194258963c1e748012a04fea56c9831` | LF | `11b9bb305556de4c8955846d432f252ec194258963c1e748012a04fea56c9831` |
| `tests/test_count_pmf_calibration_runner.py` | `fb45fa7bcc979cf9d98e5146698339277fd3dcfb` | `a8f60a8049d31931529e8e583a59d1c82aa048c6eef770b2d9d488ba10daea73` | `28cfd33fd9ab773d4ae007c9448d8e6297aa05058324a8a2f54049cba33e8dd5` | CRLF | `6db755c22a47d69d8b02593955ec3e0e35e1a86f5516bfaf05bdeb32af5d3709` |
| `research/offseason_2026/pregame_pa_ext/preflight_calibration_v1.md` (preserved) | `174e3b7f5bf5556355355c1572248db8c02d09ae` | `9962adf5e0114fb972e1bec1a4595c5363351385e95e5f98115c7e82caa919e1` | `9962adf5e0114fb972e1bec1a4595c5363351385e95e5f98115c7e82caa919e1` | LF | `9962adf5e0114fb972e1bec1a4595c5363351385e95e5f98115c7e82caa919e1` |

---

## Reconciliation of Computational & Contract Changes (`07ef1a5` → `2c716a4` → `3291fc5`)

Each item flagged in the post-`07ef1a5` review is classified below with its exact code/card location and test coverage at `3291fc5`:

| # | Review Item | Status at `3291fc5` | Implementation Location | Verification Test |
|---|---|---|---|---|
| 1 | Enforce card's 1,000-start minimum calibration sample size at runner boundary (distinct from reusable helper's 100-start minimum) | **IMPLEMENTED & TESTED** | `count_pmf_calibration_runner.py:153-156`; `count_pmf_calibration.py:110-115` | `test_runner_rejects_999_calibration_starts`, `test_runner_accepts_exactly_1000_calibration_starts` (`test_count_pmf_calibration_runner.py:150-181`) |
| 2 | Reject protected block (`confirm_2025H2`) and any unrecognized block labels loud instead of silently filtering | **IMPLEMENTED & TESTED** | `count_pmf_calibration_runner.py:137-144` (`allowed = {"block_2024H2", "block_2025H1"}`) | `test_runner_rejects_protected_block_row`, `test_runner_rejects_arbitrary_unexpected_label` (`test_count_pmf_calibration_runner.py:184-208`) |
| 3 | Reconcile isolation language to FIT-ISOLATION contract (the input frame carries both blocks' columns; evaluation outcomes are extracted only after `GuardedEvaluationLoader.freeze(fitted_a)` persists `fitted_a.json` to disk) | **IMPLEMENTED & TESTED** | `card_count_pmf_calibration_2026-10-24.md:99-104, 147-151, 185-186, 205-210`; `count_pmf_calibration_runner.py:3-12, 202-219`; `count_pmf_calibration.py:152-206` | `test_runner_observes_evaluation_load_after_persist` (`test_count_pmf_calibration_runner.py:258-290`); `test_guarded_loader_*` (`test_count_pmf_calibration.py:302-367`) |
| 4 | Remove unregistered evaluation-cohort size guard and `_skip_eval_gate` parameter | **IMPLEMENTED & TESTED** | `count_pmf_calibration_runner.py:71-76, 150-156` | Verified in runner signature and boundary tests (`test_count_pmf_calibration_runner.py:61-181`) |
| 5 | Document directional (non-symmetric) behavior of clipped linear CDF mapping (`a < 1` adds `1 - a` mass at `K=0`; `a > 1` clips `F_cal(0)` to 0 only when `a*(1 - F(0)) > 1`) | **IMPLEMENTED & TESTED** | `card_count_pmf_calibration_2026-10-24.md:35-49`; `count_pmf_calibration.py:15-24, 51-53` | `test_a_gt_1_does_not_always_zero_out_p0`, `test_clip_fires_only_when_a_times_1_minus_f0_exceeds_1`, `test_directional_not_symmetric` (`test_count_pmf_calibration.py:41-68, 171-180`) |
| 6 | Secondary diagnostic: full 24-bucket CDF calibration (`pred_cdf_frozen`, `pred_cdf_calibrated`, `empirical_cdf` for `k = 0..23`) | **IMPLEMENTED & TESTED** | `count_pmf_calibration_runner.py:277-296` | `test_runner_sequence_and_outputs`, `test_runner_secondary_diagnostics_numerical` (`test_count_pmf_calibration_runner.py:61-99, 211-236`) |
| 7 | Secondary diagnostic: own-line log loss and Brier score (`own_line_ll_frozen`, `own_line_ll_calibrated`, `own_line_brier_frozen`, `own_line_brier_calibrated`) | **IMPLEMENTED & TESTED** | `count_pmf_calibration_runner.py:298-331` | `test_runner_secondary_diagnostics_numerical` (`test_count_pmf_calibration_runner.py:211-236`) |
| 8 | Secondary diagnostic: threshold reliability evaluated at the model's own quoted half-lines (`round(E[K] + 0.5) - 0.5`) plus point-summary MAE/RMSE | **IMPLEMENTED & TESTED** | `count_pmf_calibration_runner.py:239-275` | `test_runner_secondary_diagnostics_numerical` (`test_count_pmf_calibration_runner.py:211-236`) |
| 9 | Calibration/evaluation key-overlap test uses >=1,100 starts per block and matching cohort hashes so the overlap check specifically fires | **IMPLEMENTED & TESTED** | `count_pmf_calibration_runner.py:171-191` | `test_runner_rejects_cal_eval_key_overlap` (`test_count_pmf_calibration_runner.py:238-256`) |
| 10 | Optimizer success verification and deterministic identity tie-break (`\|RPS(a) - RPS(1.0)\| <= 1e-10` selects `a = 1.0`) | **IMPLEMENTED & TESTED** | `count_pmf_calibration.py:135-149` | `test_fit_rejects_optimizer_success_false`, `test_identity_tie_rule_all_mass_at_zero` (`test_count_pmf_calibration.py:222-241, 261-271`) |

---

## Registered Input & Cohort Verification (Metadata / Keys Only — Zero Outcome Evaluation)

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

## Permitted Synthetic Test Execution Receipt at `3291fc5`

1. **Calibration unit + runner integration suite:**
   - Command: `python -m pytest tests/test_count_pmf_calibration.py tests/test_count_pmf_calibration_runner.py -q`
   - Result: **47 passed, 0 failed, 0 skipped** (`35` in `test_count_pmf_calibration.py`, `12` in `test_count_pmf_calibration_runner.py`) in `10.73s`.
2. **Full `pregame-pa-ext-v2` lane test suite (14 test files):**
   - Command: `python -m pytest tests/test_count_pmf_calibration.py tests/test_count_pmf_calibration_runner.py tests/test_attach_order_invariance.py tests/test_pregame_pa_adapter.py tests/test_market_eval_k.py tests/test_ablation_features.py tests/test_lineup_diagnostic.py tests/test_m0_multiclass.py tests/test_m0_verifications.py tests/test_m0_integration.py tests/test_count_agg_eval.py tests/test_count_aggregation_exact.py tests/test_count_aggregation_separation.py tests/test_exposure_profile.py -q`
   - Result: **185 passed, 0 failed, 0 skipped** in `29.44s`.

---

## Known Limitations & Nuances for Chat 2 Verification

1. **Line-ending sensitivity of `_code_identity()`:** `count_pmf_calibration_runner._code_identity()` hashes `Path(__file__).read_bytes()`. Because `count_pmf_calibration_runner.py` is checked out with CRLF in this Windows worktree (`50d9f988...`) while its git-blob LF hash is `10ba60e5...`, `receipt_initial.json` will record `50d9f98879e25b295f04fefd9d588803de6ae1751d9d8b470a4683737816161a` when executed in this worktree. Both hashes are pinned in the table above and in `calibration_execution_manifest_v3.json`.
2. **Own-line LL/Brier threshold definition (`count_pmf_calibration_runner.py:310-314`):** `own_line_ll_*` and `own_line_brier_*` evaluate `mk.model_p_over(pmf, mean_k)` against `o = 1.0 if k_real > mean_f else 0.0`, where `mean_f` and `mean_c` are continuous expectations (whereas `threshold_reliability` at `lines 239-241` rounds `mean_f` to the nearest half-line `round(mean_f + 0.5) - 0.5`). Because `model_p_over(pmf, line)` sums `pmf[k > line]`, any non-integer `mean_f` defines the same exceedance event `K >= floor(mean_f) + 1` as the half-line `floor(mean_f) + 0.5`, except if `mean_f` and `mean_c` cross an integer boundary in opposite directions. This affects only the secondary `own_line_ll_calibrated` / `own_line_brier_calibrated` diagnostic, not the primary `count-RPS` metric or `threshold_reliability`.

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

## STATUS: AWAITING CHAT 2 INDEPENDENT PREFLIGHT REVIEW (NOT EXECUTED)
