# REVIEW_HANDOFF — market-eval v2, everything Chat 2 needs

**Date:** 2026-10-14. Read this first; each section points at the
authoritative artifact. Companion docs (same directory):
`REVIEW_SNAPSHOT.md` (pin + hashes), `SPLIT_MAP.md`, `MOMENTS.md`,
`INCIDENT.md`, plus the spec set: `EXPERIMENT_CARD.md` (registration +
C2 corrections), `BUNDLE_EXTRACTION.md` (input lineage),
`ARTIFACT_MAP.md` (era mapping), `METRIC_SCHEMA.md` (registered vs
PROPOSED metrics), `EXCLUSION_LEDGER.md` (population reconciliation).

## Pinned snapshot

- Commit: `02ce162f119208b762edf1fd690edd5e7ee9b8ea` in this repository
  (local worktree; branch `main` at pin time), dir
  `research/offseason_2026/market_eval/`.
- All 9 committed blobs sha256-verified BYTE-IDENTICAL to the lake sources
  (manifest + hashes in REVIEW_SNAPSHOT.md). Scoped `.gitattributes`
  (`* -text`) prevents EOL drift.
- No conftest shim needed; tests self-resolve `market_eval.py` via
  `parents[1]`. Repo `testpaths = ["tests"]` keeps the snapshot out of the
  repo's default suite.
- Parquets/data excluded; lake paths (`outputs\prep_v2\`,
  `outputs\verification\`, frozen inputs) stay authoritative; prep_v2
  output hashes pinned in `outputs\prep_v2\manifest.json`.

## Exact test commands

```
:: committed bytes (repo layout; run from the repository worktree root)
python -m pytest research/offseason_2026/market_eval/tests -q

:: lake copy (private research lake, local only)
cd <private research lake>\market-eval-v1
python -m pytest tests\ -q

:: scorer end-to-end only (synthetic, known payouts + hand-computed Brier)
python -m pytest research/offseason_2026/market_eval/tests/test_score_end_to_end.py -q
```

Result 2026-10-14, run on the committed bytes: **28 passed, 0 failed**
(18 prep/guard + 10 scorer end-to-end). Synthetic fixtures only; no
archive reads; all writes inside tmp_path.

## Implemented scorer — what to review

`market_eval.py` `run_score` (line ~1220): prep-hash gate (`_prep_hash_check`,
fail loud on mismatch), realized-K join (refuses on any unmatched row),
settlement (`settle_result`: half line over wins K >= ceil(L); integer push
at K = L with refund), payout (`payout_units`), PIN metric
(`_brier_logloss`: multi-class Brier over {win, push, lose} on identical
matched contracts for H3-raw / LOG5-raw / de-vig `p_market`), paired
slate-date bootstrap (`_slate_bootstrap`: 2000 resamples, seed 20261001,
resampling unit = game_date, IDENTICAL resample indices across
competitors; paired diffs h3-market, l5-market, h3-l5), ROI ratio
bootstrap (separate stream, seed+1, documented), persisted count errors
REUSED verbatim (`PERSISTED_COUNT_COLS`, never recomputed), write-once
score dir, six outputs. EXECUTION REMAINS OWNER-GATED — **no authorized
canonical scoring run has executed**; one accidental run occurred
(2026-10-14 ~17:15, outputs deleted; INCIDENT.md; inspection status
unresolved).

## Fixed (registered before execution; no optimization)

- **Selection:** per (start, line, side): latest pre-cutoff snapshot per
  book -> BOOK_PRIORITY -> best decimal price -> name; edge gate H3-raw
  p_win > break_even + 0.02 (strict). Verified vs frozen prep:
  **0 differences on all 11,435 bets**. Eval-observation rule (one pair per
  (start, line): max total decimal -> priority -> latest ts) is separate;
  the 23,978/40,008 book-choice delta between the two rules is disclosed
  in verification_report.json (`selection_rule_delta`).
- **Settlement:** registered semantics above; push = explicit refund; zero
  integer-line contracts in cohort (registered + tested, unexercised).
- **Primary metric:** multi-class Brier at matched contracts (PIN) with
  effective counts (40,008 side rows / 20,004 pairs / 6,643 starts /
  270 slate dates) reported alongside; complementary sides NOT independent
  — slate bootstrap is the declared correlation handling.
- **Weighting:** flat 1-unit stakes; paper ROI/WR/CLV reported SEPARATELY
  from probability skill; CLV uses the bet book's OWN closing side price
  (473 bets without a close keep their row, excluded from CLV stats).

## Verified predictor-to-quote timing

`quote_time_verification` (verification_report.json): rule =
`predictor_available_ts` = forecast_cutoff 00:00 ET; actionable quotes must
be at/after it (ENFORCED in prep v2). **0 predating actionable quotes / 0
eval observations / 0 paper bets — verdict PASS (0 violations).**
7,429 post-cutoff tier-A quotes exist in the archive and are excluded.

## Tier B separation

Tier A (verified vendor commence clock; 2025-03-18..2025-09-28; 4,624
starts / 28,044 side rows) vs Tier B (snapshot-label clock proxy;
2024-07-01..2024-09-30; 2,189 starts / 11,964 side rows) carried as
separate fields and summaries end to end; Tier B is development-era by
date and is labeled sensitivity — NEVER pooled into a Tier A headline.

## Population reconciliation (kept separate — do not mix)

| Population | n | What it is |
| --- | ---: | --- |
| Payload cohort | 7,194 | 2024-07-01..2025-09-28 starts (PA + count lanes) |
| Eligible after identity exclusions | 6,813 | 7,194 - 62 unresolved - 294 unmatched - 25 doubleheader-ambiguous |
| Usable paired-contract starts | 6,643 | market-lane analysis population |
| Eval observations | 20,004 | (start, line) pairs; 40,008 (start, line, side) rows |
| Slate dates | 270 | bootstrap resampling unit |
| Paper-bet starts | 5,399 | 11,435 bets; ladder exposure (max 5 bets/start; 3,731 multi-bet starts) |

Exact reconciliation: 7,194 = 62 + 294 + 25 + 166 + 4 + 1,244 + 5,399.
7,194 vs 6,643 vs 20,004 vs 270 are NESTED populations of ONE forecast-
evaluation cohort — NOT independent samples and NOT new splits.
Count-lane persisted errors are reported both full-cohort (7,194) and
restricted to matched-contract starts (6,643), labeled separately.

## The two serious issues (lead with these in any review)

1. **Accidental scoring incident (2026-10-14 ~17:15):** the old guard test
   ran the real scorer with default paths against the real frozen prep +
   real outcomes; outputs deleted; test rewritten tmp_path-scoped; card
   discloses it. UNRESOLVED: whether anyone inspected the computed
   metrics before deletion. Consequence: treat scoring-run blinding as
   compromised-until-proven-otherwise; owner should state on record
   whether the outputs were read. Full reconstruction: INCIDENT.md.
2. **No verified historical pregame BF inputs for 2023-2025:** the BF PMFs
   in the payload are the BASE empirical per-start distribution as
   registered upstream (ARTIFACT_MAP missing-artifact #6;
   DOWNSTREAM_BF_INTEGRATION blocker). Verified pregame BF (vendor-priced
   archive / promoted hazard construction / forward persistence) does not
   exist, so **production-equivalent workload accuracy is UNCERTIFIABLE
   for 2023-2025**; any BF-layer production claim must wait on that
   blocker. The market-eval scorer evaluates the PMFs as frozen and
   discloses this lineage; it does not cure it.

## Review priorities (in order)

1. **Pooling-collision independent test** — v1 pooled K markets on a key
   omitting `player_norm`, deleting one pitcher's quotes on 750,797 shared
   (event, snapshot, book, line, side) keys and running nondeterministically
   (eval pairs 10,640-10,650 across processes). Verify v2's fix
   (load_quotes: pooling key includes player_norm; deterministic
   file-row-index tie-breaks + maintain_order unique) and reproduce
   bit-identity cross-process.
2. **RMSE/RPS formulas** — count-layer errors are PERSISTED upstream
   (start_metrics_v2) and reused verbatim; review their definitions in
   bf-workload-v1, not in this repo (this code only averages them).
3. **PMF moments** — MOMENTS.md: mixture mean/variance, independence
   approximation, PA binary variance vs K-rate uncertainty.
4. **Settlement semantics** — settle_result/payout_units + synthetic
   hand-computed cases (win/lose/push, missing close, no-bet exclusion).
5. **Split map** — SPLIT_MAP.md; confirm per-block fit-key receipts
   (executed_keys_summary.json) and the 2025H2 inspected-confirmation label.
6. **BF lineage** — BUNDLE_EXTRACTION section 4 (BASE empirical 37-cat PMF
   -> geometric tail cap 60 -> binomial combiner cap 23); identical BF PMF
   for both arms (registered upstream).
7. **Predictor provenance** — payload sha256
   `19511a49...312b58a96` (frozen pre-label-join); overnight-p2 run
   identity `6a62d8ed...6def2`; executed fit-key receipts; library pins
   (python 3.11.9, polars 1.43.0, numpy 2.4.6, sklearn 1.9.0).
8. **Incident** — INCIDENT.md; decide the blinding question.
9. **Test isolation** — synthetic fixtures only; tmp_path scoping; the
   17:15 lesson is enforced by test_score_implemented_but_requires_inputs.
10. **Population reconciliation** — exclusion ledger exactness (above);
    effective counts; ladder-exposure warning (bets within a start share
    realized K; ROI/PnL not independent per start).

## Known gaps / limits (disclosed, not blockers)

- No authorized canonical scoring run (owner-gated); one accidental run
  occurred 2026-10-14 ~17:15 (outputs deleted; inspection status
  unresolved — INCIDENT.md); market lane has no authorized registered
  outcome numbers.
- Integer-line push machinery unexercised (0 such contracts).
- Count-layer interval coverage/sharpness metrics are PROPOSED
  (METRIC_SCHEMA), not implemented/persisted.
- The 5 review docs (REVIEW_SNAPSHOT, SPLIT_MAP, MOMENTS, INCIDENT, this
  file) are committed as a docs-only follow-up commit on top of the pin;
  canonical copies also live in the private research lake
  (`<private research lake>\market-eval-v1\`, local only).
- 2026 data: CLOSED, nothing touched (no-2026-tuning rule).
