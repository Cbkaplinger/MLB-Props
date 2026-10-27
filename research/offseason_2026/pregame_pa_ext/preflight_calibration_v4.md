# SUPERSEDING PREFLIGHT RECORD — count-PMF calibration v4: execution gate (2026-10-27)

## Supersession & Lineage

This receipt **supersedes** `preflight_calibration_v3.md` (preserved byte-identical; working-tree SHA-256 recorded in its own header) and, through it, v1 and v2. No historical receipt was edited or overwritten.

The registered execution-acceptance gate added in this revision changes **only the entry-point acknowledgement and receipt provenance**. The method, cohorts, optimizer, primary metric, bootstrap, acceptance rule, and secondary-scoring definitions are unchanged: `count_pmf_calibration.py` is byte-identical to the reviewed state at `e34213a`.

| Item | Value |
|---|---|
| Worktree path | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2` |
| Branch | `research/calibration-exec-gate-v1` (from merged `origin/main` = PR #47 merge `058bee1f163e319fa767652e57152428041adaac`) |
| Gate commit | `1154988a639d6fa0b122ba8748e013931ad67d2f` |
| Superseded preflight | `preflight_calibration_v3.md` (v1/v2 preserved via v3's lineage table) |
| Superseded manifest | `calibration_execution_manifest_v4.json` (`d32409624549a337d15ffef2bd659378b12121a08d86f1a01fe65d9ab953bb80`, preserved) |
| Current manifest | `calibration_execution_manifest_v5.json` (sha256 below) |
| PR | #48 (`research/calibration-exec-gate-v1` -> `main`) |
| Execution status | **NOT EXECUTED; owner authorization not requested for this gated run yet** |

## Gate semantics (unchanged scope, new entry contract)

1. `EXECUTION_ACK_TOKEN` (`EXECUTE-COUNT-PMF-CALIBRATION-V1`) is required at both entry points:
   - **Registered CLI** (`main()`): `--execution-ack` validated BEFORE the input parquet is read, before fitting, scoring, or output creation. Missing/invalid token exits 2 with zero side effects.
   - **Direct callable** (`run_count_pmf_calibration`): keyword-only `execution_ack` required; invalid/missing raises `ValueError` before the write-once check, directory creation, receipt writing, fitting, or scoring. Omitting the keyword is also a refusal (`TypeError`).
2. `receipt_initial.json` records `execution_acknowledgement` = {token, route ("cli" | "direct-call"), note stating this is a technical gate only and NOT proof of owner authorization}. The chained `receipt_final.json` inherits it.
3. The acknowledgement token is a **technical execution-acceptance gate only**. Explicit owner authorization remains a separate procedural requirement recorded outside this code path.

## Code & Card Identity Table at Gate Commit `1154988a639d6fa0b122ba8748e013931ad67d2f`

| File (relative to repo root) | Git Object OID (SHA-1) | Git-Blob LF SHA-256 | Working-Tree Bytes SHA-256 | Changed vs `e34213a`? |
|---|---|---|---|---|
| `research/offseason_2026/pregame_pa_ext/count_pmf_calibration_runner.py` | `a982496118d6c5c056913857e4d942edfe6b80a0` | `0b3940f67b568ec1356c05de39e10772c29b67e7458b69074a204a10b69d18ad` | `e6cfc0beed31d3264cdc13b8ca1ab5e05a1608d8bf9b5dcb680a2e8960bb479a` | YES (gate + CLI + receipt field) |
| `research/offseason_2026/pregame_pa_ext/count_pmf_calibration.py` | `352b568318e797572450742a2ef683e095671038` | `e8b9e26afa8e426d2120072b50d66cdb7cb7815fdd542b44f267c06f9e368a64` | `e8b9e26afa8e426d2120072b50d66cdb7cb7815fdd542b44f267c06f9e368a64` | no (byte-identical) |
| `research/offseason_2026/pregame_pa_ext/card_count_pmf_calibration_2026-10-24.md` | `8b4ea6bb04c37bffd7032da97cf410e20f369396` | `be6c3f4ce41f0365a73f689e23cdf1ed1db7bfda0a367112039b05bff0e4f7b3` | `be6c3f4ce41f0365a73f689e23cdf1ed1db7bfda0a367112039b05bff0e4f7b3` | no (byte-identical) |
| `tests/test_count_pmf_calibration.py` | `c489ac2bb44bfbcd30c6aa8cf8f036fed2ccb113` | `11b9bb305556de4c8955846d432f252ec194258963c1e748012a04fea56c9831` | `11b9bb305556de4c8955846d432f252ec194258963c1e748012a04fea56c9831` | no (byte-identical) |
| `tests/test_count_pmf_calibration_runner.py` | `417755a1b5011927a5a5273159d93f4ec47c8611` | `238044d9d82e5433cecaccfb70126b236dec913eaa7726cd375ac4c889c25ff5` | `ea34246da667c20a09708ff43f3e9588f8e449d3f572d37e3478626e1ab7c2f3` | YES (explicit token at every synthetic call site + 7 gate tests) |

## Registered Input & Cohort Verification (unchanged; zero outcome evaluation)

| Artifact / Cohort | Full SHA-256 | Verified Match |
|---|---|---|
| `count_agg_eval_v1.parquet` (registered PMF input, 4,823 dev starts) | `afc94ad74f824b73d29e9069e17f16824786a1e8dda6395213beea64a2afaf34` | vs manifest v4 |
| `h3_raw_checkpoint.json` | `d266a1cd108633012e2bdec8c93dd467759fd966191c71aed9d790b74d1c68c6` | vs manifest v4 |
| `bf_forecasts.parquet` | `c9c2762fb2c1c239e5645c49fa92eda50bd652d26e54755ac8bf0c28fa968679` | vs manifest v4 |
| `projected_pa_probs_v1.parquet` | `fd1841e12c19b55b3259935a778c5e8815a0e37b20666b2e53d001d0adb840b8` | vs manifest v4 |
| `start_metrics_v2.parquet` | `af6814ec7ea73b4ac941dd52f185139062b987762d639203b867e15bb4817fde` | vs manifest v4 |
| Calibration cohort (`block_2024H2`, n=2,314) | `d38b10aae3fe747206b2d33588cb2729306206a91724f72b9ffc97a96522edf0` | vs manifest v4 |
| Evaluation cohort (`block_2025H1`, n=2,509) | `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7` | vs manifest v4 |
| Output directory `count_pmf_calibration_v1/` exists? | False (not executed) | verified |

## Permitted Synthetic Test Execution Receipt at Gate Commit

- Command: `python -m pytest tests/test_count_pmf_calibration.py tests/test_count_pmf_calibration_runner.py -q`
- Result: **56 passed, 0 failed, 0 skipped** (36 module, 20 runner, including 7 new gate tests) in 35.38s.
- Full suite at the same commit: **1,095 passed, 8 skipped** in 824.43s.
- Note: preflight v3 recorded the targeted count as "35 module + 14 runner"; the actual merged-baseline collection was 36 + 13 = 49. This receipt records the correct counts.

## Exact Gated Registered Invocation (DO NOT EXECUTE WITHOUT CHAT 2 DELTA REVIEW + OWNER AUTHORIZATION)

```powershell
C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\.venv\Scripts\python.exe C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2\research\offseason_2026\pregame_pa_ext\count_pmf_calibration_runner.py --pmfs C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\count_agg_eval_v1\count_agg_eval_v1.parquet --out-dir C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\count_pmf_calibration_v1 --expected-cal-hash d38b10aae3fe747206b2d33588cb2729306206a91724f72b9ffc97a96522edf0 --expected-eval-hash f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7 --n-boot 2000 --seed 20261001 --execution-ack EXECUTE-COUNT-PMF-CALIBRATION-V1
```

The prior direct-call invocation (`run_count_pmf_calibration(...)` without `execution_ack`) no longer executes: it is refused before any side effect.

## STATUS: AWAITING CHAT 2 DELTA REVIEW (NOT EXECUTED)
