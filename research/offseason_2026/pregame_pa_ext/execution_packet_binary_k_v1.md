# Execution packet: binary_k_vs_multinomial_v1

STATUS: PREPARED (command-to-CLI and disclosure-to-code checked 2026-11-03),
NOT AUTHORIZED. This packet states exactly what one authorized run is allowed
to do. Approval flow: Chat 2 packet review -> explicit owner authorization ->
single execution. The ack token `EXECUTE-BINARY-K-VS-MULTINOMIAL-V1` is a
technical gate only and is NOT authorization. Experiment card:
`docs/adr/PROPOSED-binary-k-vs-multinomial-k.md`.

## Action (exactly one)

One execution of `research/offseason_2026/pregame_pa_ext/binary_k_comparison.py`
(CLI route) comparing the binary-K challenger against the existing
multinomial-plus-W0 control on the registered cohort. No refit of the
control, no rescue variants, no second run, no production, policy, model,
ledger, or schedule change, no new data sources.

## Inputs, verified paths, and identity mechanisms

All paths below are the verified identities consumed by the accepted
`workload_personalization_w0v1` run (receipt `receipt_final.json`).

| Input | Path | Identity mechanism |
|---|---|---|
| PA source | `C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet` | File SHA-256 `1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff` - ENFORCED pre-decode (exit 1 on mismatch) |
| Projected lineups | `C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet` | File SHA-256 `b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b` - ENFORCED pre-decode (exit 1) |
| Assessment outcomes | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet` | File SHA-256 `464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa` - ENFORCED pre-decode (exit 1) |
| **Reconstruction reference** | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1\workload_per_start_v1.parquet` (accepted multinomial-plus-W0 per-start artifact, column `rps_w0_pooled`) | File SHA-256 `ae971758b70e1649e28046a8180d375872ad0172f9c8b5cc03ab74e8dfa85f79` - **ENFORCED pre-decode (exit 1); recording alone was not enforcement** |
| Cohort keys (registered block_2025H1 eligible, n=2,509) | `C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet` | Sorted-key content hash `f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7` - ENFORCED before feature construction (refusal, exit 1) |
| Raw Statcast 2024 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet` | SHA-256 `de78a1893aa21e305153f5594987f85b40e4bc0cf572484e995a1416b3c49b33` - recorded in the receipt (procedural bridge accounting; same convention as the reviewed workload runner) |
| Raw Statcast 2025 | `C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet` | SHA-256 `cb072ff830959374ae2f8a8d804a0093e77b2cf0d898fda046b44605d5c31aad` - recorded in the receipt (procedural) |

Enforcement mechanics (literal, matches the code): the four file-byte pins
(PA, lineups, assessment, reconstruction reference) are verified BEFORE any
frame decode; a mismatch prints `INPUT IDENTITY MISMATCH` and exits 1 with
zero side effects. A wrong ack exits 2 with zero side effects. The cohort
content hash, duplicate keys, and the 1e-12 reconstruction gate refuse via
exception (exit 1) at their declared stages; the reconstruction gate writes
per-start evidence BEFORE refusing so a mismatch is diagnosable, never tuned
away.

## Data scope

- Registered development inputs ONLY (the pinned paths above; the same
  artifacts consumed by the authorized workload run).
- Train window `2024-05-01..2024-12-31` (same as the workload run).
- Cohort restriction applied BEFORE feature construction.
- block_2025H2 (protected) and 2026: ZERO access, ZERO scoring.
- No new data reads beyond the pinned inputs.

## Destination

`C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\binary_k_vs_multinomial_v1` - fresh write-once directory (an existing destination refuses before any input read). Receipt chain: `receipt_initial.json` (immutable; ack, code identities, config, expected input identities) -> `receipt_final.json` (cohort identity, reconstruction evidence, output hashes, acceptance) or `failure_record.json` on any exception.

## Command (single line, copy-paste ready; execution only after authorization)

```
python research/offseason_2026/pregame_pa_ext/binary_k_comparison.py --pa-source "C:\Users\ckaplinger\MLB-Props-Research\overnight-p2\data\pa_table.parquet" --lineups "C:\Users\ckaplinger\MLB-Props-Research\pregame-state-v1\data\projected_lineups_variant_v2.parquet" --assessment "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\assessment_2025H1_v1.parquet" --raw-events "C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2024\statcast_2024_regular.parquet,C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular\2025\statcast_2025_regular.parquet" --train-start 2024-05-01 --train-end 2024-12-31 --out-dir "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\binary_k_vs_multinomial_v1" --execution-ack EXECUTE-BINARY-K-VS-MULTINOMIAL-V1 --cohort-keys "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\pregame_multiclass_baseline_v1_inputs_v2\eligible_cohort_keys_2025H1.parquet" --expected-cohort-hash f77d7a66639ee94a9157244b357487d5f462c6cb0bd4909bbffb44b924db41b7 --reconstruction-reference "C:\Users\ckaplinger\MLB-Props-Research\pregame-pa-ext-v2\diagnostics\workload_personalization_w0v1\workload_per_start_v1.parquet" --expected-reconstruction-sha256 ae971758b70e1649e28046a8180d375872ad0172f9c8b5cc03ab74e8dfa85f79 --expected-pa-sha256 1d3be6297d344a93506c9be094795c798d3e32b97dd7ce2f30523804ca846aff --expected-lineups-sha256 b6a1947c9e212be7e37159edad38a086763c7724de9aabb817c8a6384eb1488b --expected-assessment-sha256 464fe1922c4aa3090f46b43cdce4949a888ad0c20ccd269d5c2cce671a1b80aa
```

Every flag above matches the CLI argparse exactly (15/15 verified via
`--help` on 2026-11-03; none missing, none extra).

## Reporting rules (pre-declared in the card)

Statistical direction and practical magnitude are reported separately.
Statistical direction: CI entirely below zero favors binary-K; entirely
above retains the multinomial control; overlapping zero is inconclusive.
A magnitude below the declared practical threshold (0.005 count-RPS) does
not justify added complexity regardless of CI direction. Promotion is
never automatic. The reconstruction gate must pass before any contrast is
reported; a failed gate preserves its failure record and stops execution.

## Explicitly out of scope (deferred, not part of this experiment)

- The `m0.apply_multinomial` two-class softmax repair and any change to
  the reviewed `workload_comparison.py` are DEFERRED; they are recorded
  as a nonblocking finding for review and must not be expanded, retried,
  or repaired inside this run.
- No taxonomy, calibration, feature, workload, or estimator-family
  change beyond the single declared K-probability-source difference.
- No MLflow logging, no follow-up runs, no subgroup analyses.

## Limitations carried into any result

Development evidence on the registered 2025H1 cohort; not a fresh final
test; no production, betting-value, or causal claims; the binary arm
models P(K) only and says nothing about non-K class uses; 2026 untouched.
