# INCIDENT — accidental real scoring run, 2026-10-14 ~17:15

**Reconstructed from file evidence, pytest cache, and the card's disclosure.
Nothing was rerun to produce this document.**

## What happened

After the scoring code landed in `market_eval.py` (mtime 17:14:47) but
before its guard test was rewritten, a pytest run executed the OLD guard
test `tests\test_market_eval.py::test_score_flag_not_authorized`, which
invoked `me.main(["--score"])` with DEFAULT argparse paths. That ran the
real scorer against the real frozen prep with real outcomes.

## Code / input identity (what the default paths resolved to)

| Binding | Value (market_eval.py defaults) |
| --- | --- |
| Test that fired | `test_score_flag_not_authorized` (pre-C2 guard; name survives ONLY in `.pytest_cache\v\cache\{nodeids,lastfailed}`) |
| Entry point | `me.main(["--score"])` -> `run_score(...)` |
| Prep read | `DEFAULT_OUT_DIR` = `outputs\prep_v2\` — the REAL frozen prep (written 17:00:45; scoring verifies prep hashes and proceeds only on match) |
| Outcomes read | `DEFAULT_START_METRICS` = `<private research lake>\bf-workload-v1\data\start_metrics_v2.parquet` (local, not in this repo) — REAL realized K (7,194 starts) + persisted count errors |
| Outputs written | `DEFAULT_SCORE_DIR` = `outputs\score_v2\` — the six score files |

## What was computed

The full registered scoring path, once, on real data: prep hash
verification; realized-K join onto all 20,004 eval observations / 40,008
side rows; settlement of all 11,435 registered paper bets (win/lose/push,
PnL); multi-class Brier + non-push log loss for H3-raw, LOG5-raw, and
de-vig market; slate-date bootstrap (seed 20261001); CLV table; ROI
bootstrap. All six score outputs were written under `outputs\score_v2\`.

The test then FAILED its (now-obsolete) assertion — the failure is
preserved in `.pytest_cache\v\cache\lastfailed`:
`"tests/test_market_eval.py::test_score_flag_not_authorized": true`.

## What changed afterward

- `outputs\score_v2\` was DELETED (no score outputs exist under `outputs\`
  today; verified by directory listing).
- The guard test was rewritten as `test_score_implemented_but_requires_inputs`
  (test_market_eval.py:510), which passes `--prep-dir` / `--score-dir`
  INSIDE tmp_path so tests can never again reach default real paths; the
  end-to-end scorer tests are likewise tmp_path-scoped.
- The deviation note was added to EXPERIMENT_CARD.md (correction C2:
  "UNAUTHORIZED real scoring run executed accidentally at 2026-10-14 17:15
  ... its outputs were deleted without being cited and are NOT evidence of
  any kind; the authorized scoring run remains gated").
- `reports\test_results.txt` records the same note.
- Timeline cross-check: prep_v2 written 17:00:45; market_eval.py scoring
  code 17:14:47; incident ~17:15; spec docs rewritten 17:24-17:27
  (EXPERIMENT_CARD.md 17:26:36); verify_ledger.py run 17:27-17:28. The C2
  re-prep (17:00) PREDATES the incident and was caused by the pooling-key
  defect, not by the incident.

## Were any metrics inspected by anyone? — UNRESOLVED

The available evidence (file mtimes, pytest cache, card text, absence of
score outputs) cannot determine whether anyone VIEWED the computed numbers
before deletion. The card says the outputs were "deleted without being
cited," which bounds CITATION but not VIEWING. This is an unresolved
exposure question for the reviewer: the accidental run produced the exact
registered outcome metrics (Brier skill, ROI, CLV) for the confirm-era
cohort, and if they were seen, any subsequent "authorized first look"
would not be genuinely blind. **Treat scoring-run blinding as
compromised-until-proven-otherwise; the owner should state on the record
whether the 17:15 outputs were read.**

## Remaining logs / metadata

- `.pytest_cache\v\cache\{nodeids,lastfailed}` — the old guard-test name
  and its recorded failure (the only executable trace).
- EXPERIMENT_CARD.md C2 deviation note; reports\test_results.txt note.
- `outputs\verification\prep_summary_original.json` (17:27:48) — **NOT
  incident residue.** It is the byte-copy of `prep_v2\prep_summary.json`
  taken by verify_ledger.py immediately before its additive
  "verification" key was appended (verify_ledger.py:434-438). It contains
  prep counts and constants only — no outcomes, and the incident never
  wrote to prep_v2 (run_score only reads prep).
- No other score artifacts, logs, or stdout captures exist.

## Guard state after remediation

- Prep write-once (`WriteOnceError`) and score write-once both tested.
- Scoring refuses on prep-hash mismatch, missing realized K, or missing
  score inputs (`ScoreReadError`), all synthetic-tested.
- Tests cannot write outside tmp_path; the literal `--score` CLI path is
  exercised only against synthetic fixtures (test_score_end_to_end.py).
- Execution of the real scoring run remains owner-gated (card, C2).
