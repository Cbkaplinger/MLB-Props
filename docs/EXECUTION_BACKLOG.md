# MLB Props — Execution Backlog & Directive
> **This is the ONE holy file.** Single source of truth for what is approved, blocked, waiting on the user, and parked. Do NOT create parallel backlog files. When the user drags in a markdown file, reconcile it INTO this file, then it / the old file goes away. Keep it evergreen (see Evergreen Rule below).
>
> **Always open this file first** (`docs/EXECUTION_BACKLOG.md`). After every user prompt / agent turn that changes work state, update the **Session Snapshot** before ending.

## Directive (read this first, every session)
You have blanket approval for every item below marked APPROVED. Execute them **in order**; do not re-ask on anything already approved. Do not start new discovery/analysis/philosophizing until every APPROVED item is DONE or marked BLOCKED with a one-line reason. Notice something interesting mid-task? Put it in "Parking Lot," don't chase it. Report only on item completion or a true block — not every intermediate find.

### Iterative session loop (required)
1. **Read** this file (Snapshot → Waiting on user → Next steps → Standing Rules).
2. **Do** the next APPROVED item(s) only.
3. **Write back** before the turn ends:
   - Move finished work into **Just completed** (and **Done stack** if durable).
   - Refresh **Next steps (plan after this prompt)** so the following session has a concrete ordered list.
   - Add new ideas to Parking Lot; never silent-drop threads.
4. Tell the user briefly what changed and point them back here for the plan.

**Evergreen Rule (every session):** after reporting, reconcile THIS file against what actually happened — update item statuses, add new ideas to Parking Lot, and **pre-write the next session's plan** so no thread is lost. Close every session with this file reflecting "here is where we are and where we're heading next."

---

## Session Snapshot — 2026-09-01 (live policy PROMOTED)

### Just completed (this turn)
- **User: promote everything, document, push to close.**
- **PROMOTED live:** hard veto over@4.5 via kpi_policy.json quality gate + odds_board scorer; soft probation over@2.5/3.5 (probation_edge_floor=0.18, line floor 3.5→0.18).
- Docs: docs/reference/reports/live_policy_promotion_2026-09-01.md; interim skip rules marked PROMOTED.
- Tests: 	ests/test_odds_board_lines.py (9 passed) including hard-veto case.
- Pack A artifacts + research scripts included in commit set.
- **Git push:** agent will not push (repo policy); user runs push commands below.

### Done stack
| Track | Status |
| --- | --- |
| SSAC / Phase A-B / diagnosis / Item14 research | DONE |
| Pack A settle pack + bootstrap | DONE |
| Live 4.5-over veto promote | **DONE 2026-09-01** |
| Soft probation 2.5/3.5 | DONE (floors) |
| Book-quality filter | WONT_DO |
| Calib / monotone live swap | NOT promoted |

### Waiting on user
- [ ] Run git push (commands in chat) to publish.
- [ ] Keep logging real tickets / skips.
- [ ] Item 6/#12 real prices when available.

### Next steps (after push)
1. Operate under promoted veto; re-run weekly settle pack each settle week.
2. Do not hard-veto all low-line overs yet.
3. Defer calib/monotone/MLflow until next research cycle.
4. Refresh Snapshot each turn.

## Strategy Plan — 2026-09-01 (for user hole-poking)

**North star (your words):** improve **ROI**, improve **CLV / beat-close vs books**, and show a **clear positive delta over sportsbooks** — without laundering policy-search evidence as OOS edge.

**Working thesis:** The binding constraint is not “log trains in MLflow” or “sweep another 5k blend×floors.” It is **post-freeze decision policy under a side/line failure mode**, plus **honest market-skill measurement**. Post-freeze KING floor (n=74, 2026-08-22→08-31): ROI **−1.55%**, but **over −24.6% (n=45)** vs **under +29.3% (n=29)**; CLV mildly green overall (~59% beat-close on n_clv=29) while overs can show OK CLV and still lose money. That pattern says: **selection/side error, not “need a higher universal edge floor.”**

Evidence anchors: `docs/reference/reports/postfreeze_king_profile_metrics_2026-09-01.md`; live extract on deduped ledger (same lane). Hot spots: **4.5 over** n=18 ROI ≈ **−41%** WR 33%; **3.5 over** n=17 ROI ≈ **−6%**; unders on 4.5/5.5 look strong but small-n. Higher |edge| overs still lose → not fixed by “only bet monster edges.”

### The nine decisions (scenarios → recommendation)

| # | Question | If we maximize ROI/CLV/book-delta… | Recommendation |
| --- | --- | --- | --- |
| 1 | **Null lane** | A weak null that “KING beats” can fake a story. A harsh matched null that KING loses can kill a real side edge. | **Paper: illustrative / non-claim.** Redesign later as side×line stratified null on the *same* post-freeze opportunity set with real stakes only — only if we want a paper control, not to drive staking. |
| 2 | **Marcel vs Table 2a** | Same-fold ΔMAE helps the *modeling* SSAC half; it does not move CLV/ROI. | **Keep Table 2b non-subtractable** for now. Optional same-fold re-score = paper polish queue, not ops critical path. |
| 3 | **Dual Sharpe / DSR rebuild** | Rebuilding DSR on replay Sharpe cleans footnotes; it does not create edge. | **Live with documented freeze + one manuscript paragraph.** Rebuild only if we re-elevate betting-half claims (we should not). |
| 4 | **Post-freeze interim ops** | Flat 0.12 floor is funding the over bleed. Dual floors in governance (`over=0.10/under=0.08`) point the **wrong** way vs post-freeze data. | **Interim (shadow first, then promote only with gates):** (a) **pause or hard-veto 4.5 overs** (and treat 2.5/3.5 overs as probation); (b) **raise over floor** (candidate 0.16–0.18) while **keeping under at 0.12** (do not ease unders on 10-day luck); (c) **no stake up**; (d) prefer waiting on **real-ticket n** for money conclusions. Write this as a dated interim note; do **not** silently edit `KING_PROFILE`. |
| 5 | **DSR on N=5161** | Using DSR to “prove” post-freeze edge is a category error. | **Framing only:** DSR = selection-breadth diagnosis on *policy search*. Post-freeze KPI = ROI/CLV/side with CIs. No retune from DSR. |
| 6 | **Calibrate further?** | Isotonic already in the frozen stack. Recalibrating on post-freeze tickets = leakage into the evaluation window. Overs losing with sometimes-OK CLV smells like **wrong side / line**, not globally mis-scaled probs. | **Diagnose before recal:** post-freeze reliability + Brier/logloss skill **vs market** by side×line. Only open a *new* calibration challenger on a **pre-registered chrono split** that excludes the test window. Default: **no live recal this week.** |
| 7 | **Change floors?** | Universal floor ↑ cuts volume and may not stop 4.5-over toxicity. Universal floor ↓ dumps more bad overs. | Prefer **asymmetric / line-aware gates** over another global sweep. Run as **shadow ledger metrics** for 1–2 weeks; promote only if: post-freeze (and expanding) ROI improves **and** full-cohort CLV does not collapse **and** n remains usable. Mixed `runtime_floor_calibration.csv` (from 2026-07-31) is **contaminated** — do not re-pick 0.12/0.14 from it as “OOS truth.” |
| 8 | **Various lines** | 4.5 over is the clearest bleed; low-line overs fragile; mid/high unders small-n green. | Attack order: **(1) veto/restrict toxic over lines**, **(2) measure whether under edge survives without over subsidy**, **(3) only then consider line-specific models or count-layer fixes for low lines.** Don’t average all lines into one KPI. |
| 9 | **Where weak / how attack** | Weak: overs (esp. 4.5), policy-search contamination, thin CLV n, no ≥50 real tickets, champion vs monotone still unsigned. Strong: under pocket, mild CLV, modeling audit trail. | Attack sequence below — **policy & measurement first**, model retrain later, MLflow last. |

### Proposed attack sequence (maximize ROI/CLV without self-fooling)

**Phase A — Freeze the lies (0–2 days, mostly docs) — DONE 2026-09-01**  
- Manuscript: null = non-claim; DSR = search diagnosis; post-freeze table stays “not a claimed edge.”  
- One-page **Interim Post-Freeze Ops Stance** (dated): veto/probation rules above; stake flat; KING file untouched until you approve promotion.

**Phase B — Measure the failure mode (2–5 days, analysis) — DONE 2026-09-01 (initial)**  
- Post-freeze slice: side × line × |edge|: ROI, WR, CLV; Brier skill vs market.  
- Shadow score asymmetric floors / 4.5-over veto on the same opportunity universe (no live change yet).  
- Re-run weekly until promote/reject.

**Phase C — User-gated levers (when you decide)**  
- **Real-bet prices (#12):** only path to money-truth ROI; prioritize over any sweep.  
- **Champion→monotone (#9):** evidence said unders bleed softens, overs unchanged — aligned with “unders OK / overs broken,” but does **not** fix 4.5 overs by itself. Sign-off only after Phase B shadow, or explicitly defer.  
- Promote asymmetric policy to live only with pre-registered gates (e.g. trailing post-freeze n, ROI floor, CLV floor, max over exposure).

**Phase D — Model attacks (only if Phase B says “probs are wrong,” not “we bet the wrong side of a fine price”)**  
- Low-line / over-specific residual analysis; TBF/count-layer stress on 4.5; optional monotone path.  
- **Then** MLflow (Item 13) when that retrain loop starts.

**Phase E — SSAC abstract**  
- Lead modeling + honest demotion. Betting half: post-freeze transparency + no edge claim until real-ticket and/or powered OOS clears.

### Explicit non-goals (this cycle)
- Another 5k blend×floor search to chase ROI.  
- Recalibrating on the post-freeze window.  
- Stake-up on unders’ 10-day heater.  
- Treating mixed pre/post floor tables as OOS.  
- MLflow as a substitute for ops decisions.

### What I want you to poke holes in
1. Is **vetoing 4.5 overs** too aggressive (kills CLV sample / learning) vs only raising over floor?  
2. Should unders’ floor stay 0.12 or **tighten** (protect CLV) rather than “keep”?  
3. Is champion→monotone a **parallel** lever or a distraction until line veto is tested?  
4. Minimum evidence to promote shadow→live (my strawman: ≥3 weeks post-freeze **or** ≥40 shadow tickets, ROI≥0 vs status quo, CLV≥0.52 full-cohort on the gated set)?  
5. Anything I under-weighted (park factors, starter role, juice, book mix)?

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

10. **[DONE 2026-09-01]** Two-tier test-gating. Added `.pre-commit-config.yaml` (local system hook: pytest on `tests/test_odds_ledger.py tests/test_real_bets.py tests/test_registries.py`). Ran `pre-commit install`; fast subset **28 passed in ~3.9s**. Full suite remains CI-only.

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
    11-followup. **[DONE 2026-08-27 — aggregator dedupe fix]** Wired canonical `dedupe_ledger_props` into the producer + all four at-risk aggregators: `grade_odds_ledger.py` (`--status` PnL sum, `--curve` n_settled), `build_runtime_monitoring_snapshot.py` (floor/monthly/deciles use deduped; slippage segments keep raw-by-book), `edge_floor_sweep_governance.py` + `policy_calibration_uncertainty_sweep.py` (`_load_settled_ledger`), `build_daily_operator_summary.py` (`_ledger_snapshot` daily ROI/PnL). Added regression test `test_dedupe_ledger_props_pnl_not_double_counted` (proves DK+FD pair is not double-counted in PnL aggregation). All 5 files py_compile; `tests/test_odds_ledger.py` 13/13 green. **Live-verified 2026-08-27**: `grade_odds_ledger.py --status` printed `settled=643 total_pnl=+$84.51` (was 1118/+$576.15 raw; stale loop artifact +$1041.04). Regenerated `daily_kpi_loop_last_run.json` via `run_daily_kpi_loop.py --skip-notebooks` → `n_settled=653` (deduped; +~10 settled during run). **Refresh 2026-09-01**: after more settled days, deduped ledger is `settled=790 total_pnl=+$10.55` (ROI ≈ +0.05%); full-cohort CLV reconcile is `n_closed=493`, `price_devig_gt0=0.544` (was 441 / 0.551 on 2026-08-27). Note: dashboard `_dedupe_frame` keys on `book` too — only exact-dupe removal, not canonical cross-book dedupe (potential item-11 follow-up). **(Item 11 follow-up now COMPLETE; reordered to run before item 10 per user approval.)**

12. **[WAITING ON USER] Item 6 backfill** — still needs your decision-time `bet_price`/`stake`/`pnl` for the 8 confirmed tickets (Valdez, Suarez, Messick, Skenes, Melton, G.Rodriguez, Cantillo, Sasaki) plus the 9th ticket's identity, to complete the real-bet ledger write.

13. **[APPROVED — DEFERRED] Local MLflow Tracking (thin v1).** Useful when actively iterating Strikeout/TBF train or Optuna — **not** on the critical path after the SSAC audit wave. See Session Snapshot → “MLflow — what it actually helps.” Resume when you ask or when train iteration restarts; do not jump here to avoid thinking through null-lane / post-freeze ops / MAE-lane issues.

14. **[DONE research 2026-09-01 — promote gated] Granular open calibration challenger (ROI path).** Fit line / line-bucket (and optional side-aware apply) isotonic/Platt on **open 2025–2026** with chrono-safe holdout; score **post-freeze** as pure OOS on skill vs market + shadow KING ROI. Do not refit on post-freeze tickets. Do not edit live calibrator / KING without sign-off. Script: production/ops/fit_granular_open_calibration.py.


## Next Session — Open Questions & Plan (evergreen)
> **Canonical live plan lives in Session Snapshot → Next steps.** This section mirrors it and keeps historical polish notes.

**Waiting on user (blocks these):**
- [ ] Item 6: per-ticket `bet_price`/`stake`/`pnl` for the 8 + the 9th ticket's identity. Fill `REAL_TICKETS` in `production/ops/backfill_real_bets.py`, run, verify 6W–3L / +$109.80 / $455.
- [ ] Item 9: explicit sign-off to swap champion→monotone, or leave as is. (Unders bleed softens −2.72%→−1.66% but is NOT fixed either way.)
- [ ] Optional batch `git push` when *you* want remote/CI — not a per-prompt requirement.

**Ready to execute (approved, no re-ask):**
- [x] **Phase A+B** — interim stance + shadow asymmetric/line-veto metrics — DONE 2026-09-01.
- [ ] **User promote/reject decision** on `veto_4_5_over` (and/or asym over floor) — blocks live KING edit.
- [ ] **Item 13 — MLflow v1** — APPROVED but **deferred** until train/Optuna iteration resumes.
- [x] **SSAC27 Track items 5–8 + Item 10 — DONE 2026-09-01**. Future-work 9–13 parked.
- [x] Item 10: `.pre-commit-config.yaml` + hook proven on commit.
- [x] **CI fix 2026-09-01:** joblib/sklearn/lightgbm install path.

**Push:** optional, user-timed. Agent never pushes; do not treat push as per-prompt chores.

**Next session polish (optional, not blocking SSAC 1–8):**
- [ ] Regenerate `manuscript.pdf` locally (Playwright/browser).
- [ ] Optional: align dashboard `_dedupe_frame` to canonical `dedupe_ledger_props`.
- [x] **Docs freshness sweep — COMPLETE 2026-08-27** (see completed bullets historically below). **Ledger refresh 2026-09-01:** reran `clv_basis_reconcile.py` + deduped `grade_odds_ledger.py --status` — current honest ledger is `790` settled / `+$10.55` / ROI ≈ `+0.05%`; full-cohort CLV `n_closed=493`, `price_devig_gt0=0.544`. The 2026-08-27 `643 / +$84.51` figures remain valid as that day's fix-evidence snapshot only.
- [x] **Docs freshness sweep detail (2026-08-27):** Audited ALL docs, diagrams, paper (.md + rendered .html), reference/research docs, and this backlog for stale/inaccurate numbers. Results:
  - **Ledger PnL figures**: confirmed NO stale raw-row figures (1118/+$576.15/+$1,041.04/688) remain in any tracked `.md`/`.py` except this backlog's intentional old-vs-new fix-evidence table (rows 14/18/19/28/52/59) and a regression-test explanatory comment.
  - **Paper deployment-profile (paper-vs-resume discrepancy)**: reconciled Sharpe `0.4352`→`0.4438`, max-DD `0.3685`→`0.1905`, Calmar `1.1841`→`2.2903` (derived 0.4363/0.1905) against source `open_top3_transfer_manual_replay_aug21_deduped_top3_from_dedupedsweep.json` **in `manuscript.md` (6 spots) and the STALE RENDER `manuscript.html` (9 spots)** — the rendered HTML had not been regenerated after the earlier `.md` fix and still carried all the old figures. Both now agree.
  - **NEW stale find — manuscript §8.5 floor-bucketing table** was computed on the RAW ledger (`307`/`285`/`265`/`209`/`159`/`299` bets). Replaced in both `.md` and `.html` with the deduped authoritative values from `runtime_floor_calibration.csv` (`233`/`214`/`193`/`153`/`112`/`225`, ROIs `0.0396`/`0.0562`/`0.0918`/`0.0395`/`0.0864`/`0.0457`) + a point-in-time freshness note.
  - **NEW stale find — `docs/reference/governance_metric_stack.md` §1/16 Kelly**: quoted `+$8,619.27`/`172.39u` profit on the open-snapshot counterfactual lane that (a) is not derivable from the cited artifact (which stores no stake/pnl) and (b) **contradicts its own `roi=0.1138`** (0.1138×212.27u=24.2u, not 172.39u). Rewrote the block using the artifact-backed metrics + an explicit flat-stake assumption that reconciles, plus a freshness note.
  - **CIs in manuscript §8.2** (`[0.0431, 0.9997]` etc.): confirmed not regenerable from any committed artifact (`_audit_boot_ci_full.json` is a different Brier/LogLoss skill bootstrap). Point estimates corrected to authoritative values; added an explicit §8.2 provenance note that bounds are session-derived bootstrap estimates (all corrected points sit within them) so they're not confused with pinned artifact values.
  - **Reference/research/diagrams**: confirmed clean or legitimate frozen point-in-time records (e.g., `market_clv_gates.md` 2026-08-06 freeze log `330/199/72`, `floor_freeze_log.md`). `daily_kpi_protocol.md` correct. `resume-summary.{md,html}` verified already authoritative (no stale figures).
- [ ] Item-11 follow-up (optional): align dashboard `_dedupe_frame` to canonical `dedupe_ledger_props` (currently keys on `book` too, so cross-book dupes may persist in dashboard displays).

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

## SSAC27 Track — Manuscript Critical Review (added 2026-08-27)

> **Status: ACTIVE.** An MIT-professor-style critical review of `docs/paper/manuscript.md` was completed 2026-08-27 (full manuscript, model-card, both diagrams, PAPER_NOTES, and the statistical audit report; figures assessed via `make_figures.py` + captions only — **no images opened**, the model can't read them). The review's core strategic verdict: **the manuscript is really two papers stapled together.** (1) The *modeling* half — leakage-safe rate×exposure forecasting, honest trial-adjusted stats (DSR), clean audit trail — is publishable and is the right SSAC27 submission. (2) The *live-betting performance* half (ROI 0.4363, Sharpe 0.4438 on 26 bets) is underpowered (its own DSR 0.0349), self-selected, and must be demoted to "illustrative" until the policy-freeze question and a placebo/null control are resolved. **Decouple them — lead with modeling rigor.**
>
> This section turns the review's prioritized action list into executable items. Do these **IN ORDER** — they gate a credible Oct 1, 2026 abstract.

1. **[APPROVED — do first] Fix the Figure 2 numbers-to-body mismatch.** `docs/paper/make_figures.py` `fig2_model_comparison` plots Mean/Ridge/LightGBM MAE (0.0854/0.0788/0.0783) titled "248-feature screen" — but the manuscript body (Table 2a, §8.6) reports the **sparse-set (72/58-feature) parity contract** (MAE ≈ 0.0767). The figure does not match the reported numbers and is a stale 248-feature-registry artifact. Regenerate against current sparse-lane artifacts, or delete. A figure that contradicts the body is disqualifying. *(Critical — 1–2 hrs.)*
2. **[APPROVED — do second] Reconcile ECE 0.024 vs 0.0639 conflict.** §8.4 / Fig-2-reliability report "mean ECE ≈ 0.024 with no post-hoc recalibration"; the deployed profile (Table 3/A5) reports ECE 0.0639 / MCE 0.1353. The manuscript never explains why the deployed, isotonic-transfer-calibrated profile looks **2.6× worse** than the raw walk-forward stack. Either they're different lanes/populations (must be labeled as such everywhere: open / manual-26 / walk-forward, and raw vs post-cal) or there's an unexplained calibration regression. Every ECE/MCE/Brier must carry (lane, n, raw/post-cal). *(Critical — 2–4 hrs.)*
3. **[DONE 2026-08-27 — abstract rewritten]** Rewrite the abstract. Lead with the DSR/sample-size finding (currently buried at line 22); co-locate every headline metric with its 95% CI (e.g., "ROI 0.4363, 95% CI [0.03, 0.81]"); drop or heavily qualify the +24.17u / ROI / Sortino framing until item 4 resolves the policy-freeze question. *(Critical — 1–2 hrs.)*
4. **[DONE 2026-09-01 — FAIL]** Resolve policy-freeze vs. evaluation-window separation. **Audit verdict: FAIL.** The `n=26` lane slate dates are `2026-07-30`–`2026-08-17`, entirely before `KING_PROFILE_AUG2026` `frozen_utc=2026-08-21T16:10:00Z`. Live blend selection rule is `best_manual_roi_after_open_calibration_transfer_deduped` (`production/ops/live_krate_ensemble.json`, commit `8ad4681`). ROI/Sharpe/PnL reclassified as **pre-freeze policy-search evidence**; stripped from headline deployment claims in abstract + Table 3 + §8.2. Full write-up: `docs/reference/reports/ssac27_policy_freeze_audit_2026-09-01.md`. *(Was critical — completed.)*

5. **[DONE 2026-09-01]** `N=5161` enumerated as eligible blend×floor configs. Report: `docs/reference/reports/ssac27_n5161_enumeration_2026-09-01.md`. Manuscript §8.2 DSR provenance corrected (not feature×model×HP).
6. **[DONE 2026-09-01]** Chronological naive MAE baselines via `models/Strikeout-Model/research/marcel_baseline.py`; Table 2b + lane caveats. Report: `docs/reference/reports/ssac27_naive_mae_baseline_2026-09-01.md`.
7. **[DONE 2026-09-01]** Tables 3/A5 CI+lane tags (prior); equity regenerable via `docs/paper/make_figures.py` `fig_equity_top3_vs_top1()`; Fig 3 caption n/date-span/generator; honesty/slippage lineage: `docs/reference/reports/ssac27_honesty_slippage_lineage_2026-09-01.md`.
8. **[DONE 2026-09-01]** Null/placebo lanes: `production/ops/run_null_decision_lane.py`. Report: `docs/reference/reports/ssac27_null_decision_lane_2026-09-01.md`. Manuscript §8.2.2. KING less red than nulls, still negative → no decision-edge claim.

#### Completed this session — 2026-08-27 artifact inspection (numbers fixed against artifacts)
- **[DONE — item 1] Figure 2 -> body mismatch resolved.** `make_figures.py` `fig2_model_comparison()` was a hardcoded 248-feature-registry MAE bar chart (0.0854/0.0788/0.0783) titled "248-feature screen"; it was **not referenced anywhere in the manuscript** (confirmed zero `.md`/`.html` references) and contradicted the sparse-lane parity contract (MAE ≈ 0.0767). Chose the review's "or delete" option: **removed the function + its call, and deleted the stale `docs/paper/figures/fig2_model_comparison.png`**. Rationale: it could not be regenerated without a same-lane sparse naive baseline (none exists), so deleting beats emitting a mixed-lane figure. `fig4_calibration` note relabeled to the artifact-backed `ece_mean`.
- **[DONE — item 2 partial (labeling)] ECE 0.024 vs 0.0639 reconciled as different lanes.** Confirmed `phase11c_calibration/metadata.json` `ece_mean=0.0243`, `ece_max=0.0403`, `n_rows=4607`, `n_windows=3`, `source_predictions=.../phase11b_walkforward/walkforward_predictions.parquet`, `needs_recalibration=False` — i.e. the 0.024 is the **pre-deployment walk-forward 2024 diagnostic (4607 raw preds, 3 windows, raw no-recal)**, NOT deployed quality. The 0.0639/0.1353 is the **deployed 26-bet lane** (`open_top3_transfer...replay` `best.ece`). Added explicit lane-labeling + a "Lane clarification" block in `manuscript.md` §8.4/Fig 2 and in `manuscript.html`. No number changed — the two ECEs were never contradictory, just underlabeled. Remaining: extend the same (lane, n, raw/post-cal) tagging to Table 3/A5 and every other ECE/Brier mention (item 2's full scope).
- **[DONE — NEW find] §8.3 slippage-table Sharpe column was wrong in both `.md` and `.html`.** The table carried a hand-extrapolated Sharpe series (0.4438/0.4387/0.4336/0.4234) that exists in **no artifact**. The authoritative `artifacts/odds_log/slippage_sensitivity_top3_floor12_aug21.csv` reports 0.4352/0.4301/0.4250/0.4148 for the same 26-bet set. ROI/PnL/Sortino already matched. **Fixed the Sharpe column in both `manuscript.md` and `manuscript.html`** + added a source/freshness note.
- **[DONE — NEW provenance] §8.2 CI bounds ARE artifact-pinned.** The backlog previously claimed the §8.2 bootstrap CIs were "not regenerable from any committed artifact." **Inspection overturned this**: `artifacts/odds_log/quant_honesty_aug21_summary.json` contains `bootstrap_iid_ci` and `bootstrap_block_by_date_ci` that exactly match the manuscript's stated intervals. Updated the §8.2 text (`.md` + `.html`) to cite that artifact. Items 3/7 can now surface these CIs straight from the artifact.
- **[DONE — NEW provenance] N=5161 pinned; citation added.** `quant_honesty_aug21_summary.json` `n_trials=5161` (+`sr_star=0.8544`) confirmed as the DSR/PSR/power source. Added Bailey & López de Prado (2014) *The Deflated Sharpe Ratio* as reference [12] and a provenance note in §8.2. Item 5 remains open only for a per-family **breakdown** of the 5161 (the artifact stores the count, not the enumeration).
- **[DONE — item 4 — 2026-09-01 FAIL]** Policy-freeze audit. 26-bet slate dates `2026-07-30`–`2026-08-17` are entirely before `KING_PROFILE_AUG2026` freeze `2026-08-21T16:10:00Z`; blend selected via `best_manual_roi_after_open_calibration_transfer_deduped`. Reclassified ROI/Sharpe/PnL as policy-search evidence; demoted in abstract/Table 3/§8.2/resume-summary. Report: `docs/reference/reports/ssac27_policy_freeze_audit_2026-09-01.md`.

- **[DONE — item 7 tables half] CI surface + lane tags on Tables 3 & A5.** Added bootstrap 95% CI annotations to the decision-lane ROI/PnL/Sharpe/Sortino rows of Table 3 (with footnote citing `quant_honesty_aug21_summary.json`) and a matching CI footnote on Table A5 (including the pre-correction-superseded note on that artifact's Sharpe/DD/Calmar). Also added explicit `deployed 26-bet manual lane, post-isotonic-transfer, n=26` lane tags to the ECE/MCE/Brier/LogLoss rows of both tables — closing item 2's full-scope lane-tagging for Tables 3 & A5.
- **[DONE — parking-lot low-priority] §1.1 Related work + §8.7 illustrative framing.** Added a "Governed decisioning and performance evaluation" paragraph to §1.1 (Bailey–López de Prado [12] + market-skill/CLV methodology). Added an explicit "explicitly illustrative and anecdotal (n=3)" disclaimer at the top of §8.7 so the case narratives cannot be read as statistical evidence.
- **[DONE — item 7 equity half, 2026-09-01]** Equity curve now produced by `docs/paper/make_figures.py`; caption cites picks CSV + n/date-span; honesty/slippage lineage report resolves Sharpe mismatch by intentional freeze (not silent rewrite).

#### Flagged — artifact lineage inconsistency (RESOLVED 2026-09-01 by documentation freeze)
- `quant_honesty_aug21_summary.json` / `slippage_sensitivity_*.csv` keep pre-correction Sharpe/DD/Calmar (0.4352/0.3685/1.1841) as **intentional diagnostic freeze** for PSR/DSR/bootstrap; manuscript headlines use authoritative replay (0.4438/0.1905/2.2903). Report: `docs/reference/reports/ssac27_honesty_slippage_lineage_2026-09-01.md`. Do not silently rewrite honesty metrics without regenerating the DSR pipeline.


#### Strategy note — consensus / CLV / ROI / other-models grounding (recorded 2026-08-27, no code work)
Grounding for how this project holds up against sportsbooks and how results are best evaluated. Drawn from `clv_basis_reconcile.json`, `clv_snapshot.json`, model-card, and manuscript §8.2/§8.5 — recorded so the framing survives, not as new approved items.
- **Vs. consensus / sportsbooks: no demonstrated edge yet.** Full-cohort devigged beat-close rate ≈ **54.4%** (`price_devig_gt0 = 0.544`, n=493 as of 2026-09-01; was 0.551 / n=441 on 2026-08-27) and the reconcile note itself warns most K-prop lines don't move (`|clv| <= 1pp` on ~42% of props), so market-beating is near coin-flip at best; CLV skill gates still read `building_sample`. The honest defensible claim is "no proven persistent edge." To make a *consensus* comparison credible we'd need a defined devigged mid-market/timestamp consensus on the *same* matched slate universe, not just the odds-log prices we happened to capture (thin-market weakness §8.5 concedes).
- **CLV evaluation discipline:** always report the **full-cohort** devigged basis (`price_devig_gt0/ge0`), never the flattering trailing-10 or `>=0` "didn't get worse" basis — those read much higher and are not comparable skill evidence. This is a standing reporting rule, not a one-off.
- **Metric-lane split (keep):** ROI/Sharpe/Sortino = decision-*performance* (small-n, CI-wide, DSR-guarded — do NOT lead with it); CLV = market-*skill*; Brier/LogLoss/ECE + delta-over-naive = the publishable model-skill half. Other-models (naive/Marcel/career-prior baselines, item 6) is what turns "absolute MAE 0.0767" into a real skill claim.
- **Reframed why of the approved items (order unchanged):** item 5 (enumerate N=5161) → DSR auditable; item 6 (naive baseline) → delta-over-naive is the most persuasive cheap modeling upgrade; item 4 (policy-freeze audit) → gating, strip ROI/Sharpe from headlines if the date can't be drawn; item 8 (placebo/null lane) → gives the null distribution DSR rests on. No change to execution order.

**SSAC27 future-work (do NOT start before items 1–8 clear; these are post-deadline depth, not submission-gating):**
- **9.** Negative-binomial + projected-TBF-distribution mixture count-layer challengers (currently not-built per model-card / audit).
- **10.** Formal market-microstructure test for the thin-market hypothesis (§8.5), or **delete the speculation now** (15-min deletion is gating-adjacent, the test is future).
- **11.** Full interpretability atlas (conditional permutation on frozen profiles).
- **12.** Sustained production SLO tracking (latency/rollback distributions).
- **13.** Live-sample accumulation toward the DSR targets the paper itself computes (n ≈ 98 for DSR>0.5; n ≈ 147 for DSR>0.8). The only thing that ever makes the *betting* half defensible. Future — but the abstract must NOT claim betting edge before this.

## Parking Lot (new ideas noticed mid-task — do not act on these until the list above is clear)
- **Book-quality filter — WONT_DO** (user 2026-09-01): books used for lines only; usually synced.

- **Live A/B parallel ledgers:** score every opportunity under status_quo / veto_4_5 / asym16 even when only one rule is bet live.
- **Block bootstrap by game_date** for ROI/CLV CIs; do not bootstrap a line cell with n≈18 into a promote claim.
- **Real-bet first:** Item 6/#12 unblocks honest money ROI vs paper.
- **Optional soft veto:** size 2.5–3.5 overs at 0.5u instead of hard skip if learning value matters.
- Three-state action space (bet / prediction-market-watch / hold) as a cleaner replacement for the binary bet/hold flip.
- Calibration-drift monitor (recent-window WR 0.493 vs. all-time 0.534).
- Reliability/calibration bucket report (among props rated 0.7-0.8, what's the real hit rate).
- Cost-asymmetry-informed stake sizing (expected loss of missing a winner vs. betting a loser).
- Side asymmetry on real tickets: all 3 losses to date were Overs; every Under/low-line-Over hit. Worth a real-ticket side-conditional check once ledger reaches meaningful n, not a 9-shot pattern to bet on.
- **MLflow v2 (after Item 13):** Optuna callback → nested MLflow runs; log ensemble-sweep / null-lane decision metrics as separate experiments; optional Model Registry *mirror* of frozen champions (still not auto-promote).
- **W&B** only if you want hosted multi-machine dashboards; not needed for solo local research.
- **SSAC27 (MIT Sloan Sports Analytics Conference) — abstract deadline Oct 1, 2026.** Items **1–8 DONE**. Future-work 9–13 remain parked. Lead submission with modeling half; betting half stays demoted. Low-priority doc polish: move ablation/freshness self-notes to a Supplemental appendix.
