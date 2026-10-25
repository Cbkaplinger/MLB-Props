# PREFLIGHT RECORD — count-PMF calibration v1 (2026-10-24)

## Base

| item | value |
|---|---|
| merge commit | `b4dd5d9d816599a5991e10f83661fe586de5e01d` |
| base branch | `origin/main` (post-PR #34 merge) |
| follow-up branch | `research/count-pmf-calibration-v1` |
| reviewed research head | `d6ce42a73011ef11f0198a624f0572c88214f887` |
| clean tree | yes |

## Identity table

| artifact | expected full SHA-256 | actual full SHA-256 | match |
|---|---|---|---|
| count_pmf_calibration_runner.py | `1e2c82c2f7f386db2e0db5867f95ef2cd2d350947a76b8ec70fa6a24e41f752a` | same | ✓ |
| count_pmf_calibration.py | `409a17be49aba885d42c57ad15cf1ded00c3ae74374cb51c54025e736ec90059` | same | ✓ |
| card_count_pmf_calibration_2026-10-24.md | `b12a3d059b3a65bb33b65e14260bd0a4fc2cbbccb9af69c07af2e9dcf5fe9343` | same | ✓ |
| count_agg_eval_v1.parquet (registered PMF source) | `afc94ad74f824b73d29e9069e17f16824786a1e8dda6395213beea64a2afaf34` | same | ✓ |
| calibration_execution_manifest_v2.json | `35347a47ef65d4f729287898a9eda35524f776c3faa7354313e93393a6a4bdf7` | same | ✓ |

Git-blob hashes (committed tree) differ from working-tree SHA-256 because git
stores compressed objects; the working-tree SHA-256 is the contract identity.

## Cohort verification

| cohort | n | SHA-256 | match |
|---|---|---|---|
| calibration (block_2024H2) | 2,314 | `d38b10aae3fe747206b2d33588cb2729306206a91724f72b9ffc97a96522edf0` | ✓ |
| evaluation (block_2025H1) | 2,509 | `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7` | ✓ |
| overlap | 0 | — | ✓ |
| confirm_2025H2 rows in execution input | 0 | — | ✓ |

## Synthetic test results

42 tests green (count_pmf_calibration: 35, count_pmf_calibration_runner: 7).

## Exact invocation

```
python -c "
import sys; sys.path.insert(0, r'C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props-worktrees\paext-v2\research\offseason_2026')
from pregame_pa_ext.count_pmf_calibration_runner import run_count_pmf_calibration
import polars as pl
pmfs = pl.read_parquet(r'C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\count_agg_eval_v1\count_agg_eval_v1.parquet')
result = run_count_pmf_calibration(pmfs,
    r'C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\count_pmf_calibration_v1',
    expected_cal_hash='d38b10aae3fe747206b2d33588cb2729306206a91724f72b9ffc97a96522edf0',
    expected_eval_hash='f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7',
    n_boot=2000, seed=20261001)
import json; print(json.dumps(result['metrics'], indent=1, sort_keys=True))
"
```

Fresh write-once output: `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\count_pmf_calibration_v1`

## STATUS: READY FOR INDEPENDENT PREFLIGHT

All identity checks pass. Synthetic tests pass. Cohort hashes match.
Awaiting Chat 2's independent preflight, then execution authorization.
