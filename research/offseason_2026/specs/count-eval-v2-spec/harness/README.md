# count-eval-v2 shared chronological comparison harness

Registered 2026-10-15. Implements
`COMPARISON_INTERFACE_SPEC.md` — one shared chronological comparison
interface so every candidate is scored on the SAME rows, SAME folds, SAME
availability semantics, SAME metrics, differing only in the model adapter.

- Spec (canonical copy, lake):
  `C:\Users\ckaplinger\MLB-Props-Research\count-eval-v2-spec\COMPARISON_INTERFACE_SPEC.md`
  (registered 2026-10-15; sha256 of the registered original at
  implementation time:
  `cc305cefed7e213bb38be495548a85f350d9798ad11c8df90919c0ca1dbb3d78`)
- Feature/fold ground truth:
  `C:\Users\ckaplinger\MLB-Props-Research\extracted_feature_reality.md`
- Candidate registry: `CANDIDATE_MAP.md`
- Interface: `comparison.py`
- Synthetic tests (spec section 7, test-first ordering):
  `test_comparison.py`

## Files

| File | Role |
| --- | --- |
| `comparison.py` | PA-row loader (identity `(game_pk, at_bat_number, batter)`, dup/availability guards), the 4 registered folds with runtime calibration spans, adapter contract + registered adapters (P0 log5 identity; P1_B_logreg 6-feature logistic; P1_H3_replay 8-feature INCUMBENT REPLAY; LightGBM/CatBoost-style/BF-lane/hierarchical as failing-loud NOT-STARTED stubs), per-fold + pooled-dev metrics, paired slate-date bootstrap (2000 resamples, seed 20261001, block-stratified row-weighted ratio = the repaired method ported from market_eval `_slate_bootstrap`), write-once outputs under `<output_root>/<run_id>/` with run identity (sha256 of config + input hashes) |
| `test_comparison.py` | 22 synthetic-only tests: row-identity guard, availability guard, end-to-end through all four folds with a trivial adapter, identical eval rows across candidates, write-once outputs, known-answer log loss for the baseline (log5 p=b=l identity + constant-adapter hand check), log5 identity pin (tol 1e-12, mirrors `p1-harness-v2\test_log5_identities.py`), bootstrap determinism + shared resample indices, fold isolation (eval/confirm perturbations cannot move train/dev outputs), adapter contract ([0,1], length, raw/cal lanes separate), stub fail-loud, missing-feature fail-loud |
| `CANDIDATE_MAP.md` | one registered candidate table reconciling P0-P2 / B0-B3 / F0-F2 + placeholders; PA-fixed and BF-fixed lanes registered separately |

## Mirror note

The working lake copy of this harness lives at
`C:\Users\ckaplinger\MLB-Props-Research\count-eval-v2-spec\harness\` and is
kept byte-identical to this committed copy (repo copy is the versioned
canonical).

## Execution gate (spec section 8)

No real-data fit or score is authorized by this package. Running any
candidate on real data requires all synthetic tests green, frozen config
hashes in the manifest, and owner authorization consistent with the F-4
one-run gate discipline. 2026 rows stay CLOSED.

Read-only bit-identity check performed 2026-10-15 (no fits, no scores, no
outputs written): fold derivation + eval identity hashes reproduce the
executed overnight-p2 assessment keys bit-identically on all four folds —
see `CANDIDATE_MAP.md`.
