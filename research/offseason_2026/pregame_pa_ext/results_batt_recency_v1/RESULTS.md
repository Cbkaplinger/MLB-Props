# RESULTS — batter-history challenger diagnostic v1 (R60/m30), 2026-10-20

Bounded real-data diagnostic executed ONCE under owner authorization
(PR #25 contract, approved head 2d2c02f at execution time). All registered
integrity checks passed. **Primary result: the challenger is significantly
WORSE than the unchanged baseline on development log loss** — the
recency-anchored batter feature REJECTS its hypothesis.

## Headline numbers (82,817 paired development evaluation PAs)

| Metric | Baseline (frozen) | Challenger (R60/m30) | Delta (chall − base) |
| --- | --- | --- | --- |
| **Log loss (PRIMARY)** | 0.5085714457 | 0.5091916511 | **+0.0006202053** |
| Brier (supporting) | 0.1647954031 | 0.1649860802 | +0.0001906771 |

- Registered bootstrap (slate-date, block-stratified, n=2000, seed 20261001,
  null-centered with the (B+1) finite-resample correction, Holm m=1):
  **p = 0.0004997501** (2000-resample resolution floor); 95% percentile
  interval on the paired delta **[+0.0002941, +0.0009431]** — entirely
  positive (worse).
- Calibration (supporting, descriptive): baseline mean predicted 0.21367 vs
  observed 0.21461; challenger mean predicted 0.20987 vs observed 0.21461;
  challenger max decile reliability gap 0.01291.

## Interpretation (dev-only, non-promotional)

Recent form anchored to an age-weighted personal history does **not**
improve batter K probabilities here — it degrades them, with the paired
interval excluding zero on the worse side. No promotion, no downstream
use, no claim beyond this development diagnostic. The unchanged frozen
baseline remains the reference.

## Coverage and abstentions

- 4,823 eligible development starts / 43,407 projected slots / **82,817
  observed pitcher-matched evaluation PAs** (frozen keys verified:
  slots `82592f18...`, evaluation `c6568151...`).
- Abstentions (frozen record `abstentions.json`, sha256
  `66c582e070229ee02e72d07af8574af4e335d75603ae47efc000851d987e385f`):
  **59 full-run** (57 debut-date newcomers + 2 window-limited veterans
  Enns 608650 / Hart 606996), of which **43 development** and 16
  confirmation-block. Development metrics never treat the full-run total
  as a development count. Confirmation outcomes were not touched.

## Execution provenance

- Executed: 2026-10-20, single run, no retry, no overwrite. Output bundle
  (write-once, in the private lake):
  `MLB-Props-Research\pregame-pa-ext-v2\diagnostics\batt_recency_v1\`
  (`batt_recency_eval_v1.parquet` sha256 `375f25f9...e0221c`;
  `metrics.json` sha256 `517bac01...1a921`).
- Receipt: `provenance_receipt.json` in the same bundle — sections inputs /
  code_config / dev_keys / fits / metrics / outputs / abstentions /
  acceptance, all validated. MLflow transport not exercised (receipt
  on disk is the mandatory record).
- Fits: block_2024H2 n=219,078 (coef sha256 `db173def...`), block_2025H1
  n=306,791 (coef sha256 `16e4dc4b...`) — training rows identical to the
  frozen recipe's realized-PA lineage (max train dates 2024-05-01 /
  2024-08-01; confirmation rows never entered training).

## DISCLOSED DEFECT + REPAIR (transparency)

The authorized run's CLI wiring did not pass artifact paths, so the
original receipt's `inputs` section was a placeholder note (receipt-
completeness defect in code published at `084d2aa`; the evaluation itself
was unaffected). **Repair (same day, disclosed):** the `inputs` section
was completed READ-ONLY from the same frozen files the run consumed, with
a dated `receipt_repair` note inside the receipt; every other section
byte-unchanged; re-validated. The CLI wiring was fixed in code so any
future run emits complete receipts natively. No re-run, no re-fit.

Input identities (from the repaired receipt): pa_table `1d3be629...`,
preserved ledger `fd1841e1...`, checkpoint raw-file `d266a1cd...`
(registered payload pin `176fb18b...` enforced), BF `c9c2762f...`,
lineups `b6a1947c...`, freeze config `31dd78b7...`.

## State

- The ORIGINAL prediction run remains **UNACCEPTED** and unchanged
  (write-once parquet untouched).
- This diagnostic is development-only: no confirmation evaluation, no
  count-distribution validation, no betting/decision claim.
- Bundle records in this directory are SEMANTICALLY EQUIVALENT JSON
  COPIES of the lake bundle, not a repository duplicate of the
  authoritative bytes: the evaluation parquet lives ONLY in the lake
  diagnostic directory (`MLB-Props-Research\pregame-pa-ext-v2\
  diagnostics\batt_recency_v1\`) - no repository copy exists. The three
  JSON copies were byte-identical to the lake bundle at publication
  (verified 2026-10-20: metrics.json `517bac01...`, provenance_receipt.json
  `5581ed2a...`, abstentions.json `66c582e0...`) and remain subject to
  re-verification by hashing against the lake bundle, which is
  authoritative.

## ADDENDUM (2026-10-20): receipt-repair disclosure strengthened

- **Executed code identity (separate from the later publication SHA):**
  the diagnostic executed with `batt_recency.py` at git **2d2c02f**, whose
  LF-normalized sha256 ? recorded AT RUN TIME in the receipt under
  `code_config.batt_recency_py_lf_sha256` ? is
  `c645da1beb50272e3e7425ca1a780d81001769b872ce88722f698f055656dba3`
  (re-verified against the 2d2c02f blob). The later commit **044f89c**
  (CLI artifact-path fix + this results/receipt mirror) changed the file
  AFTER execution (its LF sha256 is `88c32e39...`); execution evidence
  and publication are therefore distinct identities.
- **Original receipt bytes: NOT preserved.** The repair was applied
  in place, so the pre-repair receipt file (with the placeholder inputs
  note) no longer exists on disk. This is a disclosed process flaw: a
  pre-repair copy should have been retained. What IS preserved:
  (a) the repaired receipt (published copy in this directory),
  (b) the verbatim original placeholder content of the repaired section
  ? `{"note": "no artifact paths supplied (synthetic run)"}` ?
  documented in the in-receipt `receipt_repair` note, and (c) the
  code-level guarantee that the repair touched ONLY the `inputs` section
  plus the added `receipt_repair` key (repair script assigned exactly
  those two keys; every other section byte-unchanged).
- **Exactly what was repaired:** the `inputs` section ? placeholder
  replaced by six artifact identities. CORRECTION (2026-10-20, Chat 2
  finding): those identities are NOT all consumed inputs - the diagnostic
  CONSUMED only the pa_table (`1d3be629...`) and the preserved ledger
  (`fd1841e1...`), plus code; the checkpoint (`d266a1cd...`), BF
  (`c9c2762f...`), lineup (`b6a1947c...`) and freeze-config hashes are
  CONTEXT identities from the prior registration, not consumed by this
  diagnostic. The lake receipt has been corrected to classify them
  (repair 2). No metric, fit, key, abstention, or output section was
  modified by either repair.
- **Evidence connecting the executed process to the frozen inputs** (the consumed inputs are the pa_table and the preserved ledger, plus code; the checkpoint/BF/lineup hashes are CONTEXT identities from the prior registration, not consumed by this diagnostic):
  (1) the executed code paths ? `run_diagnostic` reads the pa_table
  (adapter.load_pa_table), the preserved ledger, the checkpoint
  (adapter.load_serialized_checkpoint), the BF PMF
  (adapter.load_bf_forecasts, sha-gated against the registered pin),
  and the lineups (adapter.load_projected_lineups); (2) the repaired
  input hashes match the INDEPENDENTLY registered pins recorded in prior
  turns (BF `c9c2762f...`, lineups `b6a1947c...`, pa_table `1d3be629...`,
  checkpoint raw `d266a1cd...` / payload pin `176fb18b...`); (3) the
  frozen development key hashes were reproduced at run time
  (`82592f18...` / `c6568151...`). The input hashes are computed from
  the same frozen files the run consumed; they are factual identities,
  not reconstructed contemporaneous artifacts. The one thing that cannot
  be produced is the pre-repair receipt BYTES ? stated here rather than
  reconstructed.

## CLOSEOUT (2026-10-20, after Chat 2 review)

- **Result:** the R60/m30 batter-history challenger is REJECTED on the
  registered development comparison — paired log-loss delta
  **+0.0006202053** (challenger worse), 95% percentile interval
  **[+0.0002941, +0.0009431]** excluding zero on the worse side,
  registered p-value **0.0004997501** (Holm identical, family of one).
  Supporting: Brier +0.0001906771; challenger under-predicts (mean
  predicted 0.20987 vs observed 0.21461).
- **Validity/provenance qualification:** dev-only paired diagnostic
  (82,817 observed pitcher-matched PAs, 4,823 eligible starts of 7,194);
  single execution; frozen keys verified at run time; one disclosed
  receipt-completeness defect repaired in place the same day (consumed
  inputs = pa_table + preserved ledger, plus code; checkpoint/BF/lineup
  hashes are context identities, not consumed) with the pre-repair
  receipt bytes NOT retained — disclosed rather than reconstructed.
- **Candidate rejected; baseline retained.** The frozen baseline remains
  the reference; no promotion, no downstream use.
- **Scope of the claim:** this rejects the REGISTERED R60/m30 recipe
  (cycled-prefix-mean anchoring with this decay/weight configuration). It
  does NOT reject recency-based batter modeling generally, and it is not
  evidence about the workload/count-distribution layers.
- **Confirmation untouched:** confirm_2025H2 outcomes were never read;
  the original prediction run remains UNACCEPTED and unchanged.

Next queued item (not started): the count-aggregation/workload diagnostic
per note_count_aggregation_future_2026-10-20.md, scoped as its own
pre-registered card after this closeout.
