# Challenger SOP — how every model/feature change ships (2026-09-09)

> Master work-state: `docs/EXECUTION_BACKLOG.md`. This doc is the repeatable
> process. Follow it verbatim each time a feature or challenger is proposed,
> so round N is comparable to round 1.

## 0. Standing rules (never bypass)

Post hoc only. Chrono-safe splits (never split a date). Post-freeze window is
eval-only. No live scorer/policy/calibrator edit without sign-off + revert path.
Never mutate historical labels — append new records.

## 1. Panel freeze

- Score frozen bundle once into `artifacts/live_scores/historical_scores_YYYY_YYYY.parquet`
  (`score_historical_range.py`, resume-by-date). Never re-spin the model.
- Join set-based via `join_keys.sorted_key` on BOTH sides + cached
  `event_date_map.json` (`join_universe.py`). Every join emits
  n_in / n_matched / unmatched-why (`universe_join_audit.json` pattern).

## 2. Bins first (no bet-vs-hold framing in research)

- Per-line Brier/skill/bias/ECE vs book-close; xK bins (MAE_K, bias, skill);
  TBF tails (MAE, <15 / ≥28 error); cohorts (debut flags while cheap,
  else documented gap); season split (2025 benchmark / 2026 clean).
- Script pattern: `run_universe_cells.py` → JSON report. Pre-register cells
  BEFORE the panel exists wherever n allows a fishing expedition.

## 3. Brier contract (apples-to-apples)

- Per (start, line): y = 1{actual_K > line}.
- p_ours = raw family prob; p_ours_cal = production calibrator output.
  Verify stored == recomputed (audit script pattern: max abs diff must be 0).
- p_book = devigged consensus fair (two-way markets) or labeled vig-loaded
  implicit (over-only alts — absolute comparisons flatter us; shape only).
- Brier = mean((p−y)²); skill = book − ours. Report pooled + per-line +
  same chrono split for every challenger on the same panel subset
  (same n, same dates, same join — or label the difference).

## 4. Challenger rules

- Small first: ≤4 params, linear/logit/Platt, L2 or sample-size-regularized.
  No GBM-on-top without a linear challenger losing first.
- SINGLE-FEATURE RULE (2026-09-10): new features ablated leave-one-in, one at
  a time, on a fixed base set, same splits, ΔMAE + universe Brier each.
  Family dumps banned (no attribution). The 4-at-once age challenger is
  grandfathered pending per-term ablation.
- Ensemble testing: retrain the member(s) whose set carries the feature
  (or final58-equivalent shootout), re-blend at production weights,
  judge on universe Brier — never judge a member in isolation.
- Fit on train dates, judge on held-out dates. One pre-declared kill metric
  (default: held-out Brier gain vs bundle ≥ 0.0005 to survive).

- Train/serve match: fit trials/features must equal scoring trials/features
  (caught 2026-09-09: BB kappa fit on actual-PA but scored on projected-TBF —
  parked as limitation, never shipped).
- BERKSON RULE (2026-09-10): pitcher-level correlations conditioned on stuff
  (velo/whiff proxies) or within-pitcher changes. Survivors confound levels;
  test changes and residuals, never raw cross-sections alone.
- STABILITY GATE (2026-09-10): split-half or YoY r>=0.7 + min-n curve +
  shrinkage rule before any window/feature enters, regardless of lift.
- EXTERNAL DATA (2026-09-10): license check first (NC/CC = research only until
  cleared); coverage-split documented before use (options A/B/C); join audit
  (n_in/n_matched/unmatched-why) like any panel.

## 5. Shadow, gate, promote

- Shadow: new columns/scores beside live, zero live-path change.
- Gate: confirm on the LEDGER-joined panel (bettable universe, n≈1k) +
  full contract metrics + weekly-pack confirmation.
- Promote: user sign-off + revert path (prior bundle hashed + restorable).
  Kill: file the report, keep the code, move on. Dead ends die in days.

## 6. Metrics stage-gates

Bins (skill/bias/ECE) → adjustments → per-line calibration call →
close-skill ≥ 0 → CLV/xROI/ROI/Sharpe/drawdown → Novig fills (≥50) → stakes.
Bet-vs-hold framing lives in live ops (veto) only, never in research.
Open-beating is timing signal, not money.

## 7. Known gaps (fill when cheap)

Age column PRESENT since 2026-09-10 (`_join_age_features`, nulls kept); vet-decline cohort unblocked. `snapshot_ts` in the normalized book-line parquet is still **reconstructed** (commence-5min/5h/30h). Vendor envelope timestamps were recovered 2026-09-11 into `snapshot_envelope.parquet` — replay must join those; 12 closes have vendor_ts after commence. See `oddsapi_replay_architecture.md`. BetRivers alt-bleed in main market (median robust, QA flag); debut priors = league average (minor-league translation parked as too costly, 2026-09-10 user call); consensus CSVs gone from artifacts (deployed sidecar pattern is the fix).

## 8. Hardening log (amendments with a lived incident behind each)

- Crash contract (2026-09-10 #56): monitor scripts exit 3 on internal error.
  A traceback exiting 1 once masqueraded as a quiet YELLOW night. The runner
  buckets 3+ as failure. Never let a crash share an exit code with a verdict.
- Main-vs-alt shape check (2026-09-10 #57): every new panel filters to
  main-market (`p_book_close` not null) before scoring. Scoring challengers
  on alt shape while scoring the book on main flatters us (caught twice).
- Member-vs-member judging (2026-09-10 #57): the production ensemble beats
  single-member retrains by ~0.013 by construction. Judge member-vs-member
  or ensemble-vs-ensemble, never single-vs-ensemble.
- Best-iteration inflation (2026-09-10 #57): more trees to fit noise
  (154-vs-87 with no generalization) is a fail signal. Fix seeds/params
  across arms and report iterations.
- New-file rule (2026-09-10 #59): read back the tail of every new file +
  `--help` smoke before the first real run. A missing `__main__` guard
  burns debug rounds on silent exit-0.
- Truth placement (2026-09-10 #55): selection truth (veto, BET/HOLD) lives
  on the live board; calibration truth lives on joined panels. The paper
  ledger logs every opportunity by design — ledger overs are never leaks.
- L3 null-schema (2026-09-10 #60): build join frames with explicit schemas.
  Inference from leading null-gated rows crashes on real data.
- ASCII-only research scripts (2026-09-10 #73): non-ASCII docstrings
  (em-dash, approx) crash `--help` on cp1252 Windows consoles. Write
  scripts ASCII-only.
- Polars to_numpy has no dtype kwarg (2026-09-10 #73): use
  `.to_numpy().astype(float)`, never `.to_numpy(dtype=...)`.
- Nested policy selection (2026-09-10 #109): live veto/floors were picked
  on 2026 paper n=74; WS1c/stacker date-cuts ate 2025; harness peeked 2026
  twice. Do not retune live filters from more 2026 paper. Remaining
  September is confirmatory. Clean juiced 2025-select / 2026-judge is
  post-9/27. Replay spec: `docs/reference/oddsapi_replay_architecture.md`.
  Live plan: `docs/EXECUTION_BACKLOG.md` (pack #113 steps 0-4 built). Not
  Streamlit and not another nested experiment.
- CLV sign/scale (2026-09-11 #113.0): canonical close-minus-bet on devigged
  pairs only (`clv_pp`/`clv_pp_from_americans`). Never raw-implied vs fair
  (inherits full vig as fake CLV, ~+2.7pp) and never decision-minus-close.
  Harness, bins, and ledger attach all failed this once; fixed everywhere.
- Vendor snapshot envelopes (2026-09-11 #121): historical Odds API JSON
  wraps `timestamp/previous/next`. The normalizer dropped the wrapper.
  Reconstructed close clocks are not first-pitch closes (12 after
  commence; 173 >10 min off). Research joins must use
  `snapshot_envelope.parquet`. Never forward-fill from `next_timestamp`.
- Juiced replay book pick (2026-09-11 #123): live floors speak juiced.
  Script `juiced_replay_ledger.py` is the measurement. Next-book fallback
  after DK/FD soaks BetRivers (soft/suspect). DK+FD-only is a separate
  arm, not interchangeable with all-books ROI. 2026 juiced ROI is
  confirmatory -- do not retune live policy from it.