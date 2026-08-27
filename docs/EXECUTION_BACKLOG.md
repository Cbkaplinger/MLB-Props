# MLB Props — Execution Backlog & Directive
> **This is the ONE holy file.** Single source of truth for what is approved, blocked, waiting on the user, and parked. Do NOT create parallel backlog files. When the user drags in a markdown file, reconcile it INTO this file, then it / the old file goes away. Keep it evergreen (see Evergreen Rule below).

## Directive (read this first, every session)
You have blanket approval for every item below marked APPROVED. Execute them **in order**; do not re-ask on anything already approved. Do not start new discovery/analysis/philosophizing until every APPROVED item is DONE or marked BLOCKED with a one-line reason. Notice something interesting mid-task? Put it in "Parking Lot," don't chase it. Report only on item completion or a true block — not every intermediate find.

**Evergreen Rule (every session):** after reporting, reconcile THIS file against what actually happened — update item statuses, add new ideas to Parking Lot, and **pre-write the next session's plan** (open questions, next approved steps, decisions still waiting on the user) so no thread is lost. Close every session with this file reflecting "here is where we are and where we're heading next." This is the single file that gets dragged-in markdown folded into.

## Execution Order

1. **[APPROVED] Commit the current green working tree** (test fixes: `test_pipeline.py`, `test_pitcher_features.py`, `test_registries.py`, `test_train.py`; new observability files from the daily-improvement session). Clean baseline before anything else touches the repo.
2. **[BLOCKED — verified no-op 2026-08-27]** Split/commit `close_watcher.py` (lock hardening vs. aux-market-probe). Verified: working tree is clean, the aux-probe + late-open features are already buried together inside the broad commit `de942c3` (183 new lines in close_watcher.py among 27+ files), the pre-split backup `.py` is gone (only a stale `.pyc` remains), and there is **zero uncommitted delta to split**. The split would require a destructive rebase/filter of already-committed history — not doing that without explicit sign-off. Treat as effectively combined already; resume only if user explicitly wants the `de942c3` history rewritten.
3. **[DONE 2026-08-27 — commit 3947a7a]** Widen CI (`ci.yml`): py_compile all 60 production scripts (dynamic find, was 6 hardcoded), full 270-test suite (was 2 files), install pyproject deps `.[dev]`+scipy (was a no-op `requirements.txt` that never installed polars). Validated: 60/60 compile, 270 tests green, YAML OK.
4. **[DONE 2026-08-27 — commit 2d27ef3]** Dedupe-to-best-line as shared infrastructure. Fixed canonical `dedupe_ledger_props` to key on `(game_date, player, line, SIDE)` (was missing side — kept over/under of the same line merged, a latent bug; 22 such props in data). Wired the one canonical function into the 3 scripts still aggregating raw rows: `line_policy_settled_lookback`, `clv_basis_reconcile`, `build_automation_self_check`. Added 2 tests (over/under kept separate; best book per side). Validated: 272 tests pass; real-ledger settled 1118→643 props.
5. **[DONE 2026-08-27]** Regenerated every previously-cited number on the deduped ledger (old vs new, same ledger, apples-to-apples):
   | Metric | OLD (raw) | NEW (deduped) |
   |---|---|---|
   | Settled tickets | 1118 | 643 |
   | All-time PnL | +$576.15 | **+$84.51** |
   | All-time ROI | +2.08% | **+0.51%** |
   | Stake volume | $27,635.75 | $16,725.07 |
   | Skill-gate n_clv@floor12 | 248 | **150** |
   | Skill-gate WR | 0.534 | 0.5334 |
   | CLV beat>0 | 46.5% | 55.5% |
   | Line 4.5 all ROI | −26.4% (n=413) | −22.2% (n=244) |
   | Line 4.5 profile(≥.14) ROI | −33.3% (n=76) | −34.1% (n=52) |
   | Line 5.5 over ROI | −59.1% (n=22) | −61.8% (n=13) |
   **Headline: the all-time "green" was +2.08%/+$576 on raw; on the honest deduped ledger it is +0.51%/+$84.51 — barely above breakeven. Skill-gate n falls 248→150 (still met) and WR is essentially flat (0.534→0.5334); the edge shows in CLV, not raw WR.**
6. **[DONE (infra) + BACKFILL BLOCKED on operator prices — 2026-08-27, commit 1da4c82]** Built the append-only real-bet ledger: `src/Python/real_bets.py` (separate from paper-sim `ledger.parquet`; decision-time `bet_price`/`stake` snapshot; `append_real_bets` returns `(frame, n_appended, skipped_ids)` so no ticket can silently drop — the 8/24 failure mode); `tests/test_real_bets.py` (6 integration tests proving idempotency, in-batch dup reporting, re-append never-silent, real≠paper path, summary math, stable schema); `production/ops/backfill_real_bets.py` (holds the 8 confirmed identities Valdez U4.5 W / Suarez U4.5 W / Messick O6.5 L / Skenes U6.5 W / Melton O3.5 W / G.Rodriguez O4.5 L / Cantillo U6.5 W / Sasaki O4.5 L; refuses to write rows lacking a real decision-time price/stake — reports instead of fabricating zeros). **SATISFIES THE INTEGRATION-TEST REQUIREMENT.** Backfill WRITE is BLOCKED only on the per-ticket decision-time `bet_price`/`stake`/`pnl` (and the 9th ticket's identity+prices) which live in the user's records — fill `REAL_TICKETS` in the backfill script and rerun; complete set is 6W–3L, +$109.80/$455.
7. **[BLOCKED — no script to rewrite 2026-08-27]** CUSUM `corr_before`/`clv_before` null bug. Verified: the CUSUM/regime **regeneration script does not exist anywhere in the repo** (no source for `regime_model_report.json` / `corr_after` / `clv_after` / `cusum`; only the artifacts remain, and it's likely a deleted one-off probe like `_probe*.py`). Diagnosis captured from the surviving artifact for when the script is restored: `corr_before: null` despite `edge_win_corr_break_pos: 253` (rolling_window 40) and `clv_before: null` at `clv_break_pos: 191` — i.e. the pre-breakpoint sample window is too small/empty, so the "before" stat computes null. The rewrite needs a min-sample guard that emits an explicit `null`/`insufficient` with the n instead of an unlabelled null. Resume when the script is restored or the user provides it.
8. **[DONE (in-repo sweep) 2026-08-27 — external network call remains outside agent scope]** External-outcome recovery sweep. Verified from the ledger and stored artifacts:
   - **8/24 gap is isolated to a single day, not systemic**: `ledger.parquet` has daily rows through 8/20–8/23 and 8/25–8/27 but **0 rows on 2026-08-24** — an isolated one-day ingestion hole in an otherwise-continuous record.
   - `open_projection_quotes_raw`/`open_quotes_canonical` **end in early July entirely** (last rows ~2026-07-10/11), so they never reached August — their "0 rows for 8/24" is trivial; not the right source for recovery.
   - **Melton's real 8/25 O3.5 line is not in the paper ledger** (only other Melton dates/lines are: 8/04 U5.5, 8/15 O5.5, 8/21 O4.5, 8/26 O3.5) — same class of real-ticket data gap as 8/24.
   - **Real-ticket players are present in the paper ledger on different dates/lines** than their real bets — confirming real (real_bets.parquet) vs paper are correctly separate tracks.
   - **Recovery action**: both gaps are isolated ingestion/record flat-spots, so a targeted external odds/score call (not a systemic rebuild) is warranted; executing that network/API call is outside what the agent can run here. 8/24 outcomes are already user-confirmed (PnL not blocked); this is an auditability/completeness backfill only. Side pattern re-confirmed: all 3 real losses were Overs (Messick, G.Rodriguez, Sasaki).
9. **[EVIDENCE COMPLETE 2026-08-27 — swap still gated on user sign-off]** Champion-vs-monotone swap evidence package. The side-conditional breakdown is already fully built in `artifacts/odds_log/_audit_step4_monotone_sidebreak.json` — and it was **never actually blocked on #4-#5**: it operates on the 2025 model open universe (`config.PITCHER_TRAINING_PATH`) with its own `(pitcher+line+date)` dedupe, NOT the 2026 settled paper ledger that #4-#5 dedupe. That BLOCKED-PENDING-#4-#5 status was a false dependency. Evidence verdict (clean, complete):
   - **LODO robustness: passed** — 0/55 date-drops flipped monotone's advantage (`flip_dates: []`), pooled Brier margin +0.0135 for monotone.
   - **Overs: no change** (n=896; WR 0.4766 / ROI@fair 0.1067 identical; calib −0.0307→−0.0301).
   - **Unders: monotone improves calibration (+0.0073 on shared n=835) and reduces the unders bleed — but does NOT make it positive**: deduped under ROI@fair −0.0272 (champion) → −0.0166 (monotone). Softens but does NOT obsolete the unders-floor problem.
   - **Verdict**: swap is coherent and robust, but unders-floor still requires its own decision (not obsoleted). Per Standing Rules, the actual champion swap is NOT an approved action — it needs explicit user sign-off after this evidence is reviewed.

## New Items

10. **[APPROVED] Add a two-tier test-gating setup.** Fast pre-commit hook running only registries + real-bet-ledger integrity + dedup tests (seconds). Full 278-test suite stays in CI (widened per item 3). **Decision locked: use the `pre-commit` framework with a versioned `.pre-commit-config.yaml`** (self-installs into `.git/hooks` on first run so new clones get it automatically; a bare `.git/hooks/pre-commit` script is NOT version-controlled). Fast subset confirmed at **2.58s** (`tests/test_odds_ledger.py tests/test_real_bets.py tests/test_registries.py`, 27 tests) — ideal for the hook. Next session: write `.pre-commit-config.yaml` (local repo hook: pytest on the 3 fast files), `pre-commit install`, validate a dirty-tree commit is blocked, commit it.

11. **[PROVENANCE AUDIT — COMPLETE 2026-08-27]** Grep for every place that aggregates the ledger; confirm each historical finding's generating script and whether it used canonical `dedupe_ledger_props`, a bespoke grouping, or raw rows; flag what needs recomputation. **Verdict (evidence-backed):**
    - **CLEAN — already on the fixed canonical `dedupe_ledger_props`** (live import → round-trips fixed signature automatically): all `artifacts/odds_log/_*.py` (`_analysis_extra`, `_audit_stratify_by_epoch`, `_audit_stratify_edges`, `_calibration_deep`, `_clv_snapshot`, `_timing_results`) + production `grade_odds_ledger.py`, `build_automation_self_check.py`, `line_policy_settled_lookback`, `clv_basis_reconcile`, `weekly_kpi_report`.
    - **RESOLVED specific concern:** **favorite/dog ROI splits + line×side splits** come from `_audit_stratify_edges.py` (lines 85–124), which calls canonical `dedupe_ledger_props` — **CLEAN, no recompute.**
    - **BESPOKE but side-aware — unaffected by over/under merge bug:** `keep_best_available_lines` (`src/Python/notebook_analysis_utils.py`, keyed on `(game_date, player_name, side)`) used by `build_policy_governance_report.py` + `policy_simulator.py`. Key already includes `side`, so it never had item-4's bug. (It intentionally collapses across LINES per game/player/side — different, intended semantic, not a regression.) No recompute.
    - **AT-RISK — aggregates RAW settled rows, bypasses canonical dedupe (recompute under fixed logic):**
      - `build_runtime_monitoring_snapshot.py` `_compute_floor_table`/`_compute_monthly_regime`/`_compute_edge_deciles` (roi/pnl on raw rows). Quantified: raw settled **1118 / +$576.15**, deduped **643 / +$84.51**. The `daily_kpi_loop_last_run.json` `total_pnl=$+1041.04` is a stale raw-row artifact of this path. NOTE: `_compute_slippage_segments` segments *by book*, intentionally raw — leave it.
      - `edge_floor_sweep_governance.py` `_load_settled_ledger` (line 72): raw settled.
      - `policy_calibration_uncertainty_sweep.py` `_load_settled_ledger` (line 136): raw settled.
      - `build_daily_operator_summary.py` `_ledger_snapshot` (line 40): per-day stake/pnl/roi on raw settled rows (DK+FD pairs double-counted per day).
    - **ORPHAN — generator not in repo (same class as item 7):** `regime_model_report.json` (`is_fav`/`is_over` coefficients; 939/999-bet regime analysis) has **no source script** in the repo — only the artifact remains. Provenance cannot be confirmed; do not cite its coefficients as settled until the generator is restored.
    - **NOT AFFECTED (different data domain):** `build_board_ledger_reconciliation.py` (targets `status=="open"` slate occupancy, not settled ROI); the A1/champion side-strat audit (2025 model open universe, not the settled paper ledger — consistent with item 9).
    - **Next (approved, not blocking):** add `dedupe_ledger_props(settled)` to the four at-risk aggregators above (keeping slippage-segments raw-by-book) + a regression test. Do NOT touch the orphan regime artifact.

12. **[WAITING ON USER] Item 6 backfill** — still needs your decision-time `bet_price`/`stake`/`pnl` for the 8 confirmed tickets (Valdez, Suarez, Messick, Skenes, Melton, G.Rodriguez, Cantillo, Sasaki) plus the 9th ticket's identity, to complete the real-bet ledger write.

## Next Session — Open Questions & Plan (evergreen)
**Waiting on user (blocks these):**
- [ ] Item 6: per-ticket `bet_price`/`stake`/`pnl` for the 8 + the 9th ticket's identity. Fill `REAL_TICKETS` in `production/ops/backfill_real_bets.py`, run, verify 6W–3L / +$109.80 / $455.
- [ ] Item 9: explicit sign-off to swap champion→monotone, or leave as is. (Unders bleed softens −2.72%→−1.66% but is NOT fixed either way.)

**Ready to execute (approved, no re-ask):**
- [ ] Item 10: write `.pre-commit-config.yaml` (local repo hook, 3 fast files ~2.6s), `pre-commit install`, prove dirty-tree commit is blocked, commit.
- [ ] Item 11 follow-up: add `dedupe_ledger_props(settled)` to the 4 at-risk aggregators + a regression test; keep slippage-segments raw-by-book.

**Blocked until scripts/sign-off:**
- [ ] Item 7 (CUSUM/regime rewrite) — needs generator restored. Item 11 confirms `regime_model_report.json` is an orphan too (no source).
- [ ] Item 2 (`close_watcher.py` history split) — parked forever unless user explicitly wants `de942c3` history rewritten.

## Standing Rules (apply to all of the above)
- Never mutate historical labels (hold→bet relabeling) — always append new records instead.
- Every real-money conclusion requires ≥50 real tickets before being treated as evidence of edge. The current 9-ticket, +24.1% ROI record is now fully auditable (6W–3L, all outcomes confirmed) — a good start, not proof; don't let it drive stake-sizing yet.
- Verify settlement-rule parity (prediction-market vs. sportsbook K definitions, extra innings, early exits) before trusting any grading as final.
- Personal accounts/API keys only — never company-owned tooling for any of this.
- Do not touch `KING_PROFILE_AUG2026`, floors, staking, or the champion file without explicit sign-off after evidence is reviewed.
- A pre-registered sample-size gate that is *exactly* met (not comfortably exceeded) should be treated as "not yet conclusive" — do not size up or treat as validated edge until the sample comfortably clears the threshold with margin.

## Parking Lot (new ideas noticed mid-task — do not act on these until the list above is clear)
- Three-state action space (bet / prediction-market-watch / hold) as a cleaner replacement for the binary bet/hold flip.
- Calibration-drift monitor (recent-window WR 0.493 vs. all-time 0.534).
- Reliability/calibration bucket report (among props rated 0.7-0.8, what's the real hit rate).
- Cost-asymmetry-informed stake sizing (expected loss of missing a winner vs. betting a loser).
- Side asymmetry on real tickets: all 3 losses to date were Overs; every Under/low-line-Over hit. Worth a real-ticket side-conditional check once ledger reaches meaningful n, not a 9-shot pattern to bet on.
- **SSAC27 (MIT Sloan Sports Analytics Conference) — abstract deadline Oct 1, 2026.** Separate track from all of the above; worth returning to once the ledger/audit work settles. Not yet started; parking only.
